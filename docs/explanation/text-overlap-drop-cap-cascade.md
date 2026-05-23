# 文本重叠：Drop Cap 三级字号级联导致正文误判为公式

> 本文解释为什么含有装饰性首字母（drop cap）的 PDF 翻译后会出现新旧文本重叠，
> 以及修复方案背后的原理。对应实现：`pdf2zh/converter.py`，修复 commit `49c5aef`。

---

## 现象

翻译 `sample/error/A3_Bitner_1990_ServiceEncounters.pdf` 时，输出 PDF 的某些段落里
翻译文字和原文字叠印在一起，无法阅读。

---

## 背景：两种渲染模式

`receive_layout()` 对每个字符做二分类：

| 类型 | 渲染方式 | 坐标 |
|------|----------|------|
| **普通文字** | 翻译后排入段落，由 pdfminer 自动换行 | 相对（段落起点 + 排版偏移） |
| **公式/下标** | 以占位符 `{vN}` 保留，原样贴回 | **绝对**（原始 PDF 的 x, y） |

两种渲染互不干涉——**前提是分类正确**。一旦普通正文被误判为公式，就会同时出现在：

1. 翻译段落里（被翻译引擎替换）
2. 公式占位符的绝对位置（原文照搬）

两者叠在同一坐标 → 重叠。

---

## 根本原因：三级字号级联

### PDF 的字符结构

该 PDF 的摘要段落在**同一个 DocLayout 布局区域**（同一 `cls` 值）内包含三种字号：

```
位置    字符   字号      字体
x=46   'A'   29.82pt  Helvetica   ← 装饰性首字母（drop cap）
x=68   'S'   15.68pt  Times-Roman ← "Service" 的开头大写（中间字号）
x=79+  正文  10.58pt  Times-Roman ← 正文
```

### receive_layout() 的段落字号追踪逻辑

converter 用一个**运行时参考字号** `pstk[-1].size` 来判断后续字符是否是下标：

```python
# 下标判定
child.size < pstk[-1].size * 0.79  →  cur_v = True（公式）
```

参考字号的更新规则有两条（修复前）：

```python
if (
    child.size > pstk[-1].size        # 条件1：字号比当前大（向上更新）
    or len(sstk[-1].strip()) == 1     # 条件2：段落第2个字符（len==1，处理 drop cap）
) and child.get_text() != " ":
    pstk[-1].size = child.size
```

`len==1` 条件的设计初衷：drop cap 启动段落后，第 2 个字符的字号才是真正的正文字号，
让参考字号从 drop cap 的大字号"降下来"。这在**两级**情况下工作正常。

### 三级情况下的 bug 链

```
步骤1  'A'  (29.82pt) 启动段落 → 参考字号 = 29.82
步骤2  'S'  (15.68pt) 第2个字符，len==1 触发 → 参考字号 = 15.68   ← 降到中间值，非正文值
步骤3  'e'  (10.58pt) 下标判定：10.58 / 15.68 = 0.675 < 0.79      → 误判为下标公式 ✗
步骤4  后续所有正文字符同样被误判 → 全部变成公式占位符 {vN}
步骤5  翻译段落 + 公式占位符同时渲染在同一位置 → 重叠
```

参考字号在步骤 2 稳定到 15.68（中间值），而不是 10.58（真正的正文字号），
是因为 `len==1` 只允许**一次**向下更新，没有机制处理多级级联。

---

## 修复方案

### 核心思路

引入 `drop_cap_cascade` 布尔标志，让参考字号经过**两次**向下更新来完成三级级联，
同时在级联期间屏蔽下标误判。

### 实现细节（`receive_layout()` 局部变量）

```python
drop_cap_cascade: bool = False  # len==1 向下更新后，允许再一次级联修正
```

**触发**：`len==1` 分支发生**向下**更新时（`child.size < old_size`）：

```python
drop_cap_cascade = is_len1 and child.size < old_size
```

**消费**：下一个非空格字符，用 cascade 标志允许再做一次向下更新，然后重置：

```python
if (
    (child.size > pstk[-1].size and child.size < pstk[-1].size * 1.3)
    or is_len1
    or drop_cap_cascade          # ← 三级级联：再允许一次
) and child.get_text() != " ":
    old_size = pstk[-1].size
    pstk[-1].size = child.size
    drop_cap_cascade = is_len1 and child.size < old_size  # 非 len==1 时自动重置为 False
elif child.get_text() != " ":
    drop_cap_cascade = False     # 非空格、条件不满足时重置
# 空格字符：不重置，保留标志到下一个实质字符
```

**屏蔽误判**：下标判定加入 `and not drop_cap_cascade`：

```python
_is_subscript = (
    cls == xt_cls
    and len(sstk[-1].strip()) > 1
    and child.size < pstk[-1].size * 0.79
    and not drop_cap_cascade    # ← 级联期间屏蔽，等字号先稳定
) if pstk else False
```

屏蔽是必须的——否则 cascade 标志未消费之前，下标判定就已把字符打成 `cur_v = True`，
从而跳过 `if not cur_v:` 里的 size 更新块，cascade 永远无法发挥作用。

**重置时机**：

| 情形 | cascade 重置 |
|------|--------------|
| 空格字符 | **不重置**（中间可能有行内空格） |
| 非空格字符且更新条件满足 | 由 `is_len1 and ...` 重新计算 |
| 非空格字符且更新条件不满足 | 重置为 False |
| 新段落创建 | 重置为 False |

### 同期修复：向上更新加上限

原条件1没有上限，drop cap 的超大字号会通过"向上更新"污染参考字号：

```python
# 修复前：无上限
child.size > pstk[-1].size

# 修复后：不超过当前字号的 1.3 倍
child.size > pstk[-1].size and child.size < pstk[-1].size * 1.3
```

---

## 效果

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 第 0 页公式字符数 | 1398 | 695 |
| 公式组数 | 18 | 9 |
| 下标误判字符数 | ~700 | 0 |

---

## 调试方法

遇到类似文本重叠问题，在 `receive_layout()` 的两处加打印可快速定位：

```python
# 1. 在 size 更新处，打印 len==1 触发时的字符信息
if len(sstk[-1].strip()) == 1:
    print(f"LEN1-UPDATE: char={repr(child.get_text())} sz={child.size:.2f} old={pstk[-1].size:.2f}")

# 2. 在下标判定处，打印触发时的段落上下文
if _is_subscript:
    print(f"SUBSCRIPT: char={repr(child.get_text())} sz={child.size:.2f} para_sz={pstk[-1].size:.2f} para_text={repr(sstk[-1][:40])}")
```

关注 `para_sz`（参考字号）是否被污染到一个"中间值"——如果正文字号相对于该中间值的
比值恰好低于 0.79，就是这类 bug。

---

## 回归测试

`test/test_converter.py::TestDropCapCascade`（通过模拟段落构建循环，不依赖真实 PDF）：

- `test_drop_cap_cascade_body_text_not_formula`：三级字号场景，正文不得进入公式组
- `test_drop_cap_two_level_no_cascade`：普通两级 drop cap，正常工作
- `test_actual_subscript_still_detected`：真实下标（出现在段落第 5 个字符后）仍被检测
