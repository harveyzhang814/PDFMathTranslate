# Markdown Export Design

**Date:** 2026-05-18
**Status:** Approved

## 背景

PDFMathTranslate 已有 Word 导出能力（`--word` / `export_word.py`）。本 spec 描述在此基础上增加 Markdown 导出能力（`--markdown`），输出适合在 Obsidian 中使用的 `.md` 文档，图片以 wikilink 格式引用。

---

## 输出目录结构

```
<output_dir>/
  <stem>/           # 以 PDF 文件名（不含扩展名）命名的文件夹
    <stem>.md       # 翻译后的 Markdown 文档
    images/         # 从翻译流程中提取的图片/表格截图
      p1_figure_001.png
      p2_table_001.png
      ...
```

- `<stem>` 来自输入 PDF 的文件名（与 Word 导出的 `.docx` 命名保持一致）。
- `images/` 目录内容：从临时 `elem_dir/elements/` 通过 `shutil.copy` 拷贝，文件名不变。

---

## Markdown 内容格式

### 页面分隔

页与页之间插入 `---`（Markdown 水平线），第一页前不插入。

### 文本块

所有文本块输出为普通段落（空行分隔），不做标题检测。CJK 语言过滤逻辑与 Word 导出一致：如目标语言为 CJK，丢弃不含 CJK 字符的块（未被翻译的区域）。

### 图片与 caption

图片使用 Obsidian wikilink 格式引用，caption 渲染为斜体段落：

```markdown
![[images/p2_figure_001.png]]

*图 1 这是图注文字*
```

- caption 检测复用 `_CAPTION_RE`（与 Word 导出相同正则）。
- 图片与 caption 的空间匹配复用 `_find_nearest_figure()` 逻辑。
- 未匹配到 caption 的图片在当页文本块处理完后输出，无斜体注释。

### 示例

```markdown
翻译后的正文段落一。

翻译后的正文段落二，可能跨多行。

![[images/p1_figure_001.png]]

*图 1 这是图注*

段落三。

---

第二页正文段落。
```

---

## 模块设计

### 新文件：`pdf2zh/export_markdown.py`

**公开接口：**

```python
def export_pdf_to_markdown(
    pdf_mono_path: str,
    elem_dir: Optional[str],
    output_dir: str,          # 每任务文件夹，e.g. .../paper/
    lang_out: str = "zh",
    pages: Optional[List[int]] = None,
) -> str:                     # 返回 .md 文件路径
```

**私有辅助函数（从 `export_word.py` 复制，保持独立）：**

| 函数 | 作用 |
|---|---|
| `_sanitize(text)` | 过滤非法字符 |
| `_join_pdf_lines(text)` | 合并视觉换行 |
| `_split_paragraphs(text)` | 按段落边界拆分块 |
| `_should_include(text, lang_out)` | CJK 语言过滤 |
| `_CAPTION_RE` | caption 检测正则 |
| `_find_nearest_figure(caption, page_figures, used)` | 空间匹配 |
| `_load_figure_layout(elements_subdir)` | 读取 figures.json |
| `_parse_elem_filename(fname)` | 解析图片文件名 |

这些函数均少于 15 行，独立复制避免两模块耦合，符合 YAGNI 原则。

**内部流程：**

```
1. 创建 output_dir/images/ 目录
2. 将 elem_dir/elements/*.png 拷贝到 output_dir/images/
3. 加载 figures.json → figure_layout
4. 打开 mono.pdf（pymupdf）
5. 逐页：
   a. 写 --- 分隔符（非第一页）
   b. 提取文本块（get_text("blocks")）
   c. y 坐标翻转（pymupdf→PDF 坐标系）
   d. sort_text_blocks_by_layout() 排序
   e. 翻转回 pymupdf 坐标
   f. 遍历块：caption → 图片+斜体注释；普通块 → 空行段落
   g. 输出本页剩余未配对图片
6. 写入 output_dir/<stem>.md
```

### `high_level.py` 新增

```python
def translate_to_markdown(
    files: List[str],
    output: str = "",
    lang_in: str = "en",
    lang_out: str = "zh",
    service: str = "google",
    thread: int = 0,
    model=None,
    pages: Optional[List[int]] = None,
    skip_subset_fonts: bool = True,
    keep_pdf: bool = True,
    **kwargs,
) -> str:  # 返回 .md 文件路径
```

结构与 `translate_to_word()` 完全对称：

1. `translate(..., extract_elements=True, elements_output_dir=elem_dir)`
2. `export_pdf_to_markdown(mono_pdf, elem_dir, output_dir, lang_out, pages)`
3. `finally: shutil.rmtree(elem_dir)` + 可选清理中间 PDF

### `pdf2zh.py` CLI

新增参数（与 `--word` 对称）：

```python
parser.add_argument(
    "--markdown",
    action="store_true",
    help="Export translated content as Markdown with images in images/ subfolder.",
)
```

触发逻辑：

```python
if parsed_args.markdown:
    from pdf2zh.high_level import translate_to_markdown
    md_path = translate_to_markdown(
        files=..., output=..., lang_in=..., lang_out=...,
        service=..., thread=..., model=layout_model,
        pages=pages, keep_pdf=not parsed_args.no_pdf,
    )
    print(f"Markdown saved: {md_path}")
```

`--no-pdf` 标志同样适用于 Markdown 导出。

---

## 不在本次范围内

- 数学公式提取（`mono.pdf` 中公式为矢量图形，无文本，Markdown 中留空白）
- 标题层级检测（字体大小分析）
- `--word --markdown` 组合模式（共享翻译 pass）
- GUI 集成

---

## 文件改动汇总

| 文件 | 变更类型 |
|---|---|
| `pdf2zh/export_markdown.py` | 新建 |
| `pdf2zh/high_level.py` | 新增 `translate_to_markdown()` |
| `pdf2zh/pdf2zh.py` | 新增 `--markdown` 参数及触发逻辑 |
| `test/test_export_markdown.py` | 新建（单元测试） |
