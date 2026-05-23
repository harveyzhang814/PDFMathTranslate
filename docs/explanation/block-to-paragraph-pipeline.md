# Markdown 导出：从 PDF 文字块到段落的组装流水线

> 本文解释 `export_pdf_to_markdown` 如何把 pymupdf 提取的原始文字块组装成连贯的 Markdown 段落，以及每个设计决策背后的原因。
> 对应实现：`pdf2zh/export_markdown.py`，核心函数：`_normalize_block_text`、`_merge_broken_lines`、`sort_text_blocks_by_layout`、`export_pdf_to_markdown`。

---

## PDF 文字块是什么

pymupdf 的 `get_text("blocks")` 按空间邻近性把页面字符聚合成矩形区域，每个块返回一个七元组：

```
(x0, y0, x1, y1, text, block_no, block_type)
```

其中 `text` 是块内所有字符的拼接，**视觉换行用 `\n` 分隔**。这里的 `\n` 不代表段落结束——它仅仅是渲染时行宽被用尽时的折行位置。块的边界由 PDF 坐标系中的空间距离决定，与我们想表达的"段落"这一逻辑概念并不等价。

块与段落之间存在两种不对齐：

1. **一个块包含多个视觉行**：同一段话被列宽折为若干行，pymupdf 把它们并入同一块，行之间用 `\n` 分隔。
2. **一段话跨越多个块**：双栏 PDF 中列宽较窄，英文单词有时在词中被截断，词头和词尾分别落入相邻的两个独立块。

这两种不对齐分别由流水线的不同阶段处理。

---

## 第一步：块内软换行折叠（`_normalize_block_text`）

**问题所在**：Obsidian 和大多数 Markdown 渲染器把单个 `\n`（非空行）渲染为 `<br>`，把视觉上连续的一段话拆成若干行显示，破坏了阅读体验。

**设计思路**：每处 `\n` 都需要判断：这是"一段话内的软折行"还是"有意的结构分隔"。以下五条规则按优先级顺序应用，覆盖所有主要场景：

| 优先级 | 触发条件 | 处理方式 | 典型场景 |
|--------|----------|----------|----------|
| 1 | 前行末尾为 `-` | 去掉 `-`，直接拼接 | 英文硬连字符换行：`pro-\ncess` → `process` |
| 2 | 前行末尾为 CJK 字符 | 直接拼接，不加空格 | 中文无词间空格：`研究\n结果` → `研究结果` |
| 3 | 后行首字符为小写 ASCII | 直接拼接（去除两侧空白） | 英文单词中途截断：`Quac\nkenbush` → `Quackenbush` |
| 4 | 前行末为数字 + 后行首为数字或逗号 | 直接拼接 | 年份断开：`20\n17` → `2017`；千位分隔符：`12\n,850` → `12,850` |
| 5 | 前后行末/首均为连续大写 ASCII | 直接拼接 | 缩写截断：`UNC\nTAD` → `UNCTAD` |
| （默认）| 其他 | 在两行之间插入一个空格 | 保留英文词间边界 |

规则 5 使用正则 `_RE_TRAILING_CAPS = re.compile(r"[A-Z]+$")` 检测"前行末尾是否为连续大写字母"，而非 `text.split()[-1].isupper()`。原因是：中文文本无词间空格，`split()` 会返回包含整段中文内容的巨型 token，`isupper()` 在该 token 上为 `False`（中文字符不满足 `isupper()`），导致误判为"非缩写"。`_RE_TRAILING_CAPS` 只扫描字符串末尾的连续大写字母序列，完全不受前缀内容影响。

---

## 第二步：阅读顺序排序（`sort_text_blocks_by_layout`）

**问题所在**：pymupdf 返回的块顺序是 PDF 内部流的存储顺序，对于双栏学术论文，这一顺序通常交错混乱：左栏块→右栏块→左栏块……直接输出为 Markdown 会把左右两栏的内容打乱。

**设计思路**：`text_order.py` 中的 `sort_text_blocks_by_layout` 使用几何算法检测列布局，按"先列后行"的阅读顺序重排块列表。具体逻辑是：先用列间距（gutter）把块分配到左栏或右栏，再在每栏内按 y 坐标排序，最后把两列合并为线性序列。

**坐标系注意**：pymupdf 使用 y-from-top 坐标，而 `sort_text_blocks_by_layout` 期望 PDF 标准的 y-from-bottom 坐标。排序前需翻转：

```python
flipped = [{**b, "y0": ph - b["y1"], "y1": ph - b["y0"]} for b in blocks]
sorted_blocks = sort_text_blocks_by_layout(flipped, page.rect.width, ph, avg_w)
```

排序返回的块已经是重建后的顺序，`y0`/`y1` 仍是翻转后的值，但后续步骤只依赖 `content`，所以坐标不需要再翻回去。

---

## 第三步：跨块断词合并（`_merge_broken_lines`）

**问题所在**：双栏 PDF 中，英文单词有时在列宽处被截断——词头在块 N 的末尾，词尾在块 N+1 的开头。这是两个独立的 pymupdf 块（与 `_normalize_block_text` 处理的块内 `\n` 性质不同），输出为 Markdown 时会形成两个以空行分隔的"段落"，读起来是断的。

**与第一步的区别**：

| | `_normalize_block_text` | `_merge_broken_lines` |
|---|---|---|
| 操作对象 | 单个块内部的 `\n` | 相邻两个块之间的拼接 |
| 触发时机 | 块提取阶段，每块独立处理 | 阅读顺序排序之后，整页块列表上扫描 |
| 效果范围 | 块内软换行 | 跨块词中断行 |

**规则**：扫描排序后的块列表，若满足以下两个条件，则把后一块的内容直接拼接到前一块（不加空格）：

1. 前一块末尾字符**不在**句子终止集合 `{.!?。！？…}` 中
2. 后一块首字符是**小写 ASCII 字母**（英文单词继续）

中文不做此合并——中文在任意字符边界自然断行，不存在"词被截断"的情况。

---

## 第四步：块到 Markdown 段落（一对一映射）

经过前三步处理，每个块的 `content` 已经是一段连贯文字。`export_pdf_to_markdown` 的输出逻辑很简单：

- 每个块的文字输出为一行，后面跟一个空行 → 形成 Markdown 段落（两个 `\n` 分隔）
- 若块被 `_is_caption` 判定为图注，则用斜体包裹 `*caption text*`，并在其前插入对应图片的 Obsidian wikilink `![[images/pN_figure_001.png]]`
- 每页末尾插入 `---` 页分隔符

这里隐含了一个假设：**一个 pymupdf 块 ≈ 一个段落**。在学术论文正文中，这个假设通常成立——每个视觉矩形区域对应一个逻辑段落。

---

## "块 = 段落"假设的边界

### 成立的场景

学术论文正文的主体部分：一段连续文字占据一个视觉矩形，pymupdf 把它聚合为一个块，经过软换行折叠后输出为一个 Markdown 段落。这是最常见的情况。

### 失效的场景

**跨块段落合并未完全实现**：`_merge_broken_lines` 只处理跨块的词中截断（后块首字母为小写）。如果一段话在某个完整单词末尾被折成两个块（后块首字母大写），两个块仍会输出为两个段落。这是目前已知但未修复的限制。

**一块包含多个逻辑段落**：表格行、带行内脚注的文字有时会被 pymupdf 聚合进同一个块。此时一个块会被输出为一整段，逻辑上应该是多段。

**字符间距渲染问题**：部分 PDF 标题或章节标题以字符间距方式排版（如 `R E V I E W  A R T I C L E`），每个字母独立定位，pymupdf 提取时在字母之间插入空格。这不是换行问题，不属于本流水线的处理范围，无法通过 `_normalize_block_text` 修复。

---

## 流水线总览

```
pymupdf get_text("blocks")
    │
    ▼ _normalize_block_text（块内软换行折叠）
    │   - 去连字符 / CJK 直连 / 小写续词 / 数字续接 / 大写缩写续接
    │
    ▼ 过滤（空块、水印、页眉页脚、元素区域重叠）
    │   → 详见 markdown-export-quality.md
    │
    ▼ sort_text_blocks_by_layout（阅读顺序排序）
    │   - pymupdf y-from-top → 翻转 → 列感知排序 → 输出顺序块列表
    │
    ▼ _merge_broken_lines（跨块断词合并）
    │   - 前块末非句终 + 后块首小写 ASCII → 直接拼接
    │
    ▼ 一块一段落输出
        - 普通块 → 一行文字 + 空行
        - Caption 块 → 图片 wikilink + 斜体文字 + 空行
        - 页边界 → ---
```

---

## 相关文档

- [markdown-export-quality.md](markdown-export-quality.md) — 四类噪声过滤器的原理（水印、页眉页脚、元素重叠），与本文的流水线互补
- [how-to/export-markdown.md](../how-to/export-markdown.md) — 如何使用 `--markdown` 选项的操作指南
