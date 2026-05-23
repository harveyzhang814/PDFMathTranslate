# Markdown 导出质量：PDF 文本提取的陷阱与对策

> 本文解释为什么从 mono.pdf 提取文字时会产生四类排版噪声，以及每种对策背后的原理。
> 对应实现：`pdf2zh/export_markdown.py`。

---

## 背景：mono.pdf 里有什么

翻译管道的输出物是 **mono.pdf**（单语译文）。它由 `translate_stream()` 在原始 PDF 的字节流上就地修改而成，流程如下：

```
原始 PDF → pdfminer 解析字符 → 翻译 → 重新渲染 → mono.pdf
```

关键事实：**mono.pdf 保留了原始 PDF 的全部页面结构和字符坐标**，只有被翻译引擎处理过的文字段落会被替换为中文。这意味着：

- 被 DocLayout 判定为 "abandon"（页眉/页脚等）的区域——字符仍在 PDF 里，未被翻译也未被删除
- 被检测为 "table" 或 "figure" 的区域——字符仍在 PDF 里，只是打上掩码（`layout[y][x] = 0`）阻止翻译，但 pymupdf 仍然可以读到

`export_pdf_to_markdown` 使用 pymupdf 的 `get_text("blocks")` 扫描 mono.pdf，因此会把上述"残留"字符当作普通正文提取出来，产生噪声。

---

## 四类噪声及对策

### 1. 竖排水印文字 → `_is_vertical_text_block()`

**现象**：每个字符单独一行，连续几百行，拼起来是类似 `Downloaded from https://...` 的侧边版权水印。

**原因**：Wiley 等期刊在 PDF 页边打印旋转 90° 的水印。pymupdf 处理旋转文字时，把每个字形存为独立的单行文字块，或把所有字形合并为一个块但每字符一行（换行符分隔）。

**对策**：检测块内每行平均长度 ≤ 2 且总行数 ≥ 5 的块，直接丢弃。该判断针对 **mono.pdf 的块结构**（原始 PDF 中同一水印可能存储为一整行长字符串，但经过翻译管道重渲染后变为逐字符换行形式）。

```python
def _is_vertical_text_block(text: str) -> bool:
    non_empty = [l for l in text.split("\n") if l.strip()]
    if len(non_empty) < 5:
        return False
    return sum(len(l) for l in non_empty) / len(non_empty) <= 2.0
```

---

### 2. 页眉/页脚 → `_is_header_footer()`

**现象**：`756 | MARIANI ET AL.`、`Psychol Mark. 2022;39:755–776.`、`wileyonlinelibrary.com/journal/mar` 等混入正文。

**原因**：DocLayout 的 "abandon" 类在原始 PDF 上正确屏蔽了这些区域（阻止翻译），但 mono.pdf 里这些字符依然存在。pymupdf 不知道它们是页眉/页脚。

**对策**：基于 y 坐标位置过滤——块完全位于页面顶部 8% 或底部 8% 的区域内即丢弃。8% 适配学术期刊双栏排版的页眉/页脚带宽，可通过 `margin` 参数调整。

```
页面坐标（pymupdf y from top）：
  [0 ──── 8%  ]   ← 页眉区
  [8% ─── 92% ]   ← 正文区（保留）
  [92% ── 100%]   ← 页脚区
```

---

### 3. 英文单词中途断行 → `_merge_broken_lines()`

**现象**：`...创造性角色（Quac` / `kenbush，` 作为两个独立段落输出。

**原因**：双栏 PDF 的列宽迫使英文单词在视觉行末断开，pdfminer 把每个视觉行提取为独立的文字块。reading-order 排序后这些块仍然相邻，但它们会被输出为两个以空行分隔的"段落"。

**对策**：排序后扫描相邻块对——若上一块末尾字符不是句子终止标点，且下一块首字符是小写 ASCII 字母（英文单词继续），则直接拼接（不加空格）。中文不做此合并，因为中文在字符边界自然断行不需要修复。

---

### 4. 图片/表格区域文字重复 → `_block_overlaps_element()`

**现象**：`![[images/p5_table_001.png]]` 正确出现后，同一张表格的数据行（`United States`, `1,622`, `29`…）又以纯文字形式出现一遍。

**原因**：DocLayout 检测到 "table" 区域后，翻译管道在该区域打掩码（阻止翻译），并将该区域的截图保存为 PNG。但 mono.pdf 里表格字符依然存在（掩码只影响翻译，不删除字符），pymupdf 正常提取。

**对策**：两步走——

**Step 1**：`high_level.py` 在保存图片截图时，同步把每个表格（和图形）在页面坐标系中的 bounding box 写入 `elements/tables.json`（图形已有 `figures.json`）。坐标系为 pymupdf y-from-top，与 mono.pdf 页面一致。

**Step 2**：`export_pdf_to_markdown` 加载 `figures.json` + `tables.json`，对每个文字块计算"块面积被元素区域覆盖的比例"（IoB，intersection-over-block），若 ≥ 50% 则丢弃。

```
IoB = 交集面积 / 文字块面积
```

使用 IoB（而非 IoU）的原因：文字块通常比元素区域小得多，用 IoU 会使阈值无意义；IoB 确保"完全被元素包含的小文字块"被正确过滤。

---

## 坐标系备忘

| 场景 | x 原点 | y 原点 | 使用场景 |
|---|---|---|---|
| DocLayout 输出 | 左 | 上（pixmap） | 检测 bbox，裁剪图片 |
| pymupdf `get_text("blocks")` | 左 | 上（page） | `export_markdown.py` 文字提取 |
| pdfminer `LTChar` | 左 | **下**（PDF 标准） | `converter.py` 字符渲染 |
| `layout` 数组 | 左 | **下**（翻转后） | `converter.py` 区域掩码 |
| `figures.json` / `tables.json` | 左 | 上（pymupdf page） | bbox 过滤 |

`_extract_page_text_blocks` 和 `_is_header_footer` / `_block_overlaps_element` 均工作在 **pymupdf page 坐标**（y from top），与 `figures.json` / `tables.json` 一致，无需坐标翻转。

reading-order 排序前需将 pymupdf 坐标翻转为 PDF 坐标，排序后恢复，见 `export_pdf_to_markdown` 源码注释。

---

## 过滤顺序

`_extract_page_text_blocks` 依次应用四个过滤器：

```
get_text("blocks")
    │
    ▼ 过滤 1：空块 / 单字符块（len <= 1）
    │
    ▼ 过滤 2：竖排水印块（avg line len <= 2 且 >= 5 行）
    │
    ▼ 过滤 3：页眉/页脚（y 坐标在边距区）
    │
    ▼ 过滤 4：图片/表格区域重叠块（IoB >= 50%）
    │
    └─► 干净的文字块列表
```

顺序有意义：过滤 1/2 先去除低信噪比的大批噪声，减少后续过滤器的计算量；过滤 4 依赖外部文件，放在最后便于在无 `elem_dir` 时跳过。

---

## 局限性

- **过滤 3（页眉/页脚）** 使用固定 8% 边距，对页眉特别高（超过页面高度 8%）的期刊可能失效。可通过调整 `margin` 参数覆盖。
- **过滤 4（元素重叠）** 依赖 `tables.json` 的存在。若翻译时未启用 `--extract-elements`（即 `--word` 或 `--markdown` 之外的普通翻译），过滤 4 自动跳过（传入空列表）。
- `tables.json` 中的 bbox 是 **原始 PDF 页面**上的坐标，假设 mono.pdf 页面尺寸与原始一致（`translate_stream` 不改变页面尺寸，这一假设目前成立）。
