# 扫描版 PDF 文字重叠：位图背景与 OCR 文字层的冲突

**适用范围**：`pdfinterp.py` → `PDFPageInterpreterEx.process_page()` &
`high_level.py` → `translate_patch()`

---

## 问题现象

翻译扫描版 PDF（如 Wiley 发布的学术论文扫描件）后，输出的 mono.pdf 每一页都出现**原文英文（扫描图片）与翻译中文叠印**的现象。即使 drop cap 级联 bug 已修复，重叠依然存在。

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

`translate_patch()` 针对每一页：

1. 新建一个空 xref，替换页面的 content stream（`set_contents()`）
2. 调用 `PDFPageInterpreterEx.process_page(page)`
3. `process_page()` 最终生成：
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

## 修复方案

### 修改一：`high_level.py` — 扫描页检测

在 `translate_patch()` 内，**在** `set_contents()` 替换 content stream **之前**检测扫描页：

```python
# 检测必须在 set_contents() 之前；替换内容流后 get_image_rects() 返回空列表
mu_page = doc_zh[page.pageno]
page_area = mu_page.rect.width * mu_page.rect.height
device.page_is_scanned = False
if page_area > 0:
    for img_info in mu_page.get_images(full=True):
        xref_img = img_info[0]
        rects = mu_page.get_image_rects(xref_img)
        if rects:
            img_area = rects[0].width * rects[0].height
            if img_area / page_area >= 0.7:
                device.page_is_scanned = True
                break
```

**判定条件**：单张图片面积 ÷ 页面面积 ≥ 0.70 → 认定为扫描页。

**为什么必须在 `set_contents()` 前**：`set_contents()` 将页面的 content stream 替换为空 xref，导致 `get_image_rects()` 找不到 `Do` 指令，返回空列表。若在替换后检测，所有页面都会误判为非扫描页。

### 修改二：`pdfinterp.py` — 白色底纹注入

在 `process_page()` 的 obj_patch 构建处，当 `page_is_scanned=True` 时插入白色填充矩形：

```python
if getattr(self.device, "page_is_scanned", False):
    page_w = abs(x1 - x0)
    page_h = abs(y1 - y0)
    white_bg = f"1 1 1 rg 0 0 {page_w:f} {page_h:f} re f "
else:
    white_bg = ""
self.obj_patch[page.page_xref] = (
    f"q {ops_base}Q {white_bg}1 0 0 1 {x0} {y0} cm {ops_new}"
)
```

**渲染顺序**：

```
q [ops_base] Q            ← 绘制位图（位于 q/Q 独立坐标上下文中）
1 1 1 rg 0 0 W H re f    ← 白色矩形覆盖整页（抹除位图视觉效果）
1 0 0 1 x0 y0 cm          ← 坐标系平移（对齐 cropbox 偏移）
[ops_new]                  ← 中文翻译文字（渲染在白色底纹上）
```

**坐标系说明**：
- `q {ops_base} Q` 之后，坐标系恢复到初始 CTM（`(1,0,0,1,-x0,-y0)`）
- 白色矩形使用 `0 0 page_w page_h`，在此 CTM 下恰好覆盖整个 cropbox 区域
- 之后 `1 0 0 1 x0 y0 cm` 将坐标系平移回原点，供 `ops_new` 文字定位

---

## 对普通 PDF 的影响

- **正常 PDF**（非扫描）：`page_is_scanned=False`，逻辑不变，无白底注入
- **含图表的 PDF**：图表通常小于页面面积的 70%，不触发扫描页检测
- **极少数情况**：若 PDF 故意使用全页白色背景图片，会触发检测但白色矩形覆盖白色背景无可见影响

---

## 调试方法

```python
# 在 translate_patch() 内，set_contents 前加打印
print(f"Page {page.pageno}: page_is_scanned={device.page_is_scanned}")

# 验证 mono.pdf 的 content stream 是否含白色底纹
import pymupdf
doc = pymupdf.open("output/xxx-mono.pdf")
stream = doc.xref_stream(doc[0].get_contents()[0])
print(b"1 1 1 rg" in stream)  # 应为 True（扫描页）
```

---

## 回归测试

`test/test_scanned_pdf.py`：

| 测试类 | 测试 | 验证内容 |
|--------|------|---------|
| `TestScannedPageDetection` | `test_full_page_image_detected_as_scanned` | 全页图片 → 检测为扫描页 |
| `TestScannedPageDetection` | `test_text_only_page_not_scanned` | 纯文字页 → 不触发检测 |
| `TestScannedPageDetection` | `test_small_image_not_scanned` | 小图 → 不触发检测 |
| `TestScannedPageDetection` | `test_detection_before_set_contents` | set_contents 后检测失效（反证设计正确性） |
| `TestWhiteRectInsertion` | `test_scanned_page_has_white_rect_in_patch` | page_is_scanned=True → obj_patch 含白底 |
| `TestWhiteRectInsertion` | `test_non_scanned_page_has_no_white_rect` | page_is_scanned=False → obj_patch 无白底 |
| `TestWhiteRectInsertion` | `test_white_rect_covers_full_page` | 白色矩形尺寸等于页面尺寸 |
