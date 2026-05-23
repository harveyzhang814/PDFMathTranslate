# 文本重叠：Drop Cap 三级字号级联的根因与修复

**适用范围**：`converter.py` → `TranslateConverter.receive_layout()`

---

## 问题现象

某些 PDF（尤其是含装饰性首字母 drop cap 的学术论文）翻译后，输出页面出现**新文本与原文本重叠**。具体表现：摘要等大段正文完全消失，翻译结果叠印在原始文字上。

---

## 系统背景

`receive_layout()` 逐个处理 `LTChar` 字符对象，将它们分为两类：

- **文字**（`cur_v = False`）：进入段落栈 `sstk`，翻译后以**相对排版**方式重新渲染
- **公式/角标**（`cur_v = True`）：进入公式组 `var`，翻译后以**绝对坐标**固定在原始 (x, y) 位置渲染

只要字符被误判为公式，它就会用绝对坐标渲染，而翻译段落又会独立渲染在同一位置，于是两套内容叠加 → **重叠**。

---

## 角标检测逻辑

```python
_is_subscript = (
    cls == xt_cls                       # 与前一个字符在同一段落
    and len(sstk[-1].strip()) > 1       # 段落内已有 2+ 个字符
    and child.size < pstk[-1].size * 0.79  # 字号显著小于段落参考字号
)
```

阈值 0.79 来源于实践：LaTeX 生成的上下标约为基础字号的 70–76%，大写字母约 79%，取中间值。

段落参考字号 `pstk[-1].size` 的更新规则（修复前）：

```python
if (child.size > pstk[-1].size          # 当前字符比参考字号大
    or len(sstk[-1].strip()) == 1       # 或者是段落第 2 个字符（len==1）
) and child.get_text() != " ":
    pstk[-1].size = child.size
```

`len==1` 分支的设计意图：处理两级 drop cap，即大写首字母（如 50pt）后跟正文（如 10pt）——用第 2 个字符的字号覆盖掉首字母字号，使参考字号回到正文水平。

---

## 根本原因：三级字号级联

当 PDF 在同一 DocLayout 区域内存在**三个**不同字号时，`len==1` 只能处理一次向下更新：

```
'A'  29.82pt (Helvetica)   ← drop cap 装饰首字母
'S'  15.68pt (Times-Roman) ← 单词"Service"开头，小型大写（中间字号）
'e'  10.58pt (Times-Roman) ← 正文
```

**级联过程**：

| 步骤 | 处理字符 | 触发条件 | 参考字号变化 |
|------|---------|---------|------------|
| 1 | `'A'` 29.82pt | 新段落初始化 | → 29.82 |
| 2 | `'S'` 15.68pt | `len==1` 分支（第 2 个字符）| 29.82 → **15.68** |
| 3 | `'e'` 10.58pt | 角标检测：10.58 / 15.68 = **0.675 < 0.79** | 误判为角标 ✗ |

第 2 步将参考字号稳定到中间值 15.68（而非正文的 10.58），导致第 3 步起所有正文字符（比值 ≈ 0.67）都被误判为角标公式。

---

## 为什么两级 drop cap 不出问题

```
'A'  50pt → 段落参考字号 = 50
'n'  10pt → len==1 → 参考字号更新为 10
'd'  10pt → 10/10 = 1.0，不是角标 ✓
```

两级情况下，`len==1` 一步就把参考字号稳定到正文水平，后续字符比值为 1.0，不触发角标判定。

三级情况下，`len==1` 只更新一次（15.68），参考字号停在中间，正文字符（10.58）的比值落在角标区间内。

---

## 修复方案

### 修改一：size 向上更新加 1.3× 上限

```python
# 修复前
child.size > pstk[-1].size

# 修复后
child.size > pstk[-1].size and child.size < pstk[-1].size * 1.3
```

防止段落内出现的大字号装饰字符（drop cap 本身位于文字区域时）直接将参考字号拉高。

### 修改二：`drop_cap_cascade` 标志

```python
# 在段落字号更新块内：
is_len1 = len(sstk[-1].strip()) == 1
if (is_upward_bounded or is_len1 or drop_cap_cascade) and char != " ":
    old_size = pstk[-1].size
    pstk[-1].size = child.size
    # len==1 且向下更新 → 字号还未稳定，允许再更新一次
    drop_cap_cascade = is_len1 and child.size < old_size
elif char != " ":
    drop_cap_cascade = False   # 非空格字符才重置（空格保留标志）
```

```python
# 在角标检测处：
_is_subscript = (
    cls == xt_cls
    and len(sstk[-1].strip()) > 1
    and child.size < pstk[-1].size * 0.79
    and not drop_cap_cascade   # 字号稳定期间不误判角标
)
```

**执行路径（三级级联场景）**：

```
'A'  29.82pt → 段落初始化，size=29.82，cascade=False
'S'  15.68pt → len==1，size 更新 29.82→15.68，cascade=True（向下更新）
'e'  10.58pt → cascade=True → 角标判定被屏蔽 → cur_v=False
               → drop_cap_cascade 条件触发，size 更新 15.68→10.58，cascade=False
'r'  10.58pt → 10.58/10.58=1.0，不是角标 ✓，cascade=False
```

**空格不重置标志的原因**：'S'（15.68pt）和第一个正文字符之间存在行内空格（由字符间距逻辑插入到 `sstk`），若空格重置 `cascade`，标志在到达 'e' 之前就已被清除，修复失效。

---

## 调试方法

遇到类似"公式误判导致文本重叠"问题，可在 `receive_layout()` 内加临时打印：

```python
# 在 _is_subscript 判断处
if _is_subscript:
    print(f"SUB y={child.y0:.1f} sz={child.size:.2f} para_sz={pstk[-1].size:.2f} "
          f"ratio={child.size/pstk[-1].size:.3f} text={repr(sstk[-1][:30])}")

# 在 len==1 更新处
if is_len1 and child.size != pstk[-1].size:
    print(f"LEN1-UPDATE sz {pstk[-1].size:.2f}→{child.size:.2f} char={repr(child.get_text())}")
```

观察 `para_sz` 的演变路径，判断是否存在中间字号停留。

---

## 回归测试

`test/test_converter.py::TestDropCapCascade`：

| 测试 | 验证内容 |
|------|---------|
| `test_drop_cap_cascade_body_text_not_formula` | 三级级联（29pt→15pt→10pt）正文不进公式组 |
| `test_drop_cap_two_level_no_cascade` | 普通两级 drop cap 仍正常工作 |
| `test_actual_subscript_still_detected` | 段落第 5+ 位的真实下标仍被检测 |
