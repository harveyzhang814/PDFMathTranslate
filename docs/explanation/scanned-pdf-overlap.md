# 扫描版 PDF 文字重叠：位图背景与 OCR 文字层的冲突

**适用范围**：`pdf2zh/debackground.py`（后处理模块）、`high_level.py`（调用点）

---

## 问题现象

翻译扫描版 PDF（如 Wiley 发布的学术论文扫描件）后，输出的 mono.pdf 每一页都出现**原文英文（扫描图片）与翻译中文叠印**的现象。

---

## 根本原因

### 扫描版 PDF 的结构

此类 PDF 由两层叠加而成：

```
┌─────────────────────────────────────────┐
│  层 1（底层）：全页位图图片              │
│   CCITTFaxDecode 1-bit TIFF 扫描件       │
│   原始纸质论文的光学图像                 │
│   内含可见的英文正文                     │
├─────────────────────────────────────────┤
│  层 2（顶层）：OCR 文字层               │
│   字体名：HiddenHorzOCR                  │
│   文字渲染模式 Tr=3（不可见）            │
│   OCR 识别的文字坐标与图片对齐           │
└─────────────────────────────────────────┘
```

**关键事实**：视觉上看到的英文字母来自底层**位图**，而非顶层文字层。顶层文字层是透明的，仅供文字搜索和选取使用。

### 翻译管道的行为

`translate_patch()` 针对每一页，`PDFPageInterpreterEx.process_page()` 生成：

```
obj_patch[xref] = f"q {ops_base}Q 1 0 0 1 {x0} {y0} cm {ops_new}"
```

其中：
- **`ops_base`**：原始页面所有**非文字**指令的直接复制，包括 `q 594 0 0 792 0 0 cm /Im0 Do Q`（全页位图绘制命令）
- **`ops_new`**：翻译后重排版的中文文字块（BT...ET 序列）

结果：位图先被绘制，中文覆盖其上——但英文位图依然可见，造成**英中叠印**。

### 为什么 `ops_base` 包含位图指令

`execute()` 过滤了所有 T* 文字指令（Tj、TJ、Tf 等），但**没有**过滤图片绘制指令（`Do`、`q`、`Q`、`cm`）。这些指令被完整保留进 `ops_base`。设计意图是保留插图、图表等内容——对扫描版 PDF 的全页背景位图则产生了副作用。

---

## 修复方案：后处理模块 `debackground.py`

**设计原则**：核心翻译管道（`pdfinterp.py`、`high_level.py`）代码保持不变，白色底纹注入作为独立的**后处理步骤**，仅在输出的 mono PDF 中检测到扫描页时才介入。

### 架构

```
translate_stream()
  └─► translate_patch()         ← 核心管道，不感知扫描页，代码不变
  └─► mono_bytes = doc_zh.write(...)
  └─► mono_bytes = debackground_scanned_pages(mono_bytes)  ← 后处理
  └─► return mono_bytes, dual_bytes
```

### `debackground_scanned_pages(pdf_bytes, threshold=0.70)`

1. 用 pymupdf 打开翻译后的 mono PDF
2. 对每一页调用 `_is_scanned_page(page, threshold)`
3. 若检测为扫描页，调用 `_insert_white_rect(stream, page_w, page_h)` 修改 content stream
4. 若无任何页面被修改，原样返回 `pdf_bytes`（零开销）

### `_is_scanned_page(page, threshold=0.70)`

```python
for img_info in page.get_images(full=True):
    rects = page.get_image_rects(img_info[0])
    if rects:
        img_area = rects[0].width * rects[0].height
        if img_area / page_area >= threshold:
            return True
```

**判定条件**：单张图片面积 ÷ 页面面积 ≥ 阈值（默认 70%）

### `_insert_white_rect(stream, page_w, page_h)`

利用正则表达式定位 ops_base 与 ops_new 的分界点（`Q 1 0 0 1 ... cm BT`），在此处插入白色填充矩形：

```
q [ops_base] Q              ← 绘制位图（q/Q 独立坐标上下文）
q 1 1 1 rg 0 0 W H re f Q  ← 白色矩形覆盖整页（q/Q 隔离颜色状态）
1 0 0 1 x0 y0 cm            ← 坐标系平移
[ops_new]                   ← 中文翻译文字（渲染在白色底纹上）
```

**为什么白色矩形必须用 `q/Q` 包裹**：`1 1 1 rg` 设置非描边颜色（nonstroking color），文字渲染也使用 nonstroking color。若不隔离，白色颜色状态会渗透到 `ops_new`，使翻译文字变成白色（白底白字，不可见）。

**正则模式**：
```python
pattern = re.compile(
    rb"(.*\bQ\s+)"
    rb"(1 0 0 1 [\d. -]+cm\s+BT\s)",
    re.DOTALL,
)
```

若模式未匹配（非管道输出的 content stream），返回 `None`，跳过该页而不破坏内容。

---

## 后处理 vs 内联修复的取舍

| 维度 | 后处理（当前方案） | 内联修复（已废弃） |
|------|-------------------|--------------------|
| 核心代码改动 | 无（pdfinterp / high_level 不变） | pdfinterp + high_level 均修改 |
| 误触发风险 | 低（仅在翻译完成后的独立 pass 中介入） | 高（set_contents 前需精确时序） |
| 可测试性 | 高（debackground.py 可独立测试） | 低（需 mock 整个翻译管道） |
| 性能 | 略有开销（需重新打开 PDF） | 零额外开销 |
| 普通 PDF | 无修改，直接返回原字节 | 无修改（靠 page_is_scanned=False） |

---

## 对普通 PDF 的影响

- **正常 PDF**（非扫描）：图片面积 < 70%，`_is_scanned_page` 返回 False，`modified_count=0`，返回原始字节，**零改动**
- **含图表的 PDF**：图表通常远小于页面面积 70%，不触发
- **极少数情况**：若 PDF 故意使用全页白色背景图片，会触发检测，但白色矩形覆盖白色背景无可见影响

---

## 调试方法

```python
import logging
logging.getLogger("pdf2zh.debackground").setLevel(logging.DEBUG)

# 或直接调用
from pdf2zh.debackground import debackground_scanned_pages
result = debackground_scanned_pages(open("output/xxx-mono.pdf", "rb").read())

# 验证 content stream 是否含白色底纹
import pymupdf
doc = pymupdf.open(stream=result)
stream = doc.xref_stream(doc[0].get_contents()[0])
print(b"1 1 1 rg" in stream)  # 应为 True（扫描页）
```

---

## 回归测试

`test/test_scanned_pdf.py`（14 个测试，全部 model-free）：

| 测试类 | 测试数 | 验证内容 |
|--------|--------|---------|
| `TestIsScannedPage` | 4 | 全页图 / 纯文字 / 小图 / 自定义阈值 |
| `TestInsertWhiteRect` | 6 | 插入位置 / q-Q 包裹 / 尺寸正确 / 文字顺序 / 未知流返回 None / 原内容保留 |
| `TestDebackgroundScannedPages` | 4 | 扫描页有白底 / 普通页不变 / 混合 PDF 只改扫描页 / 阈值参数 |
