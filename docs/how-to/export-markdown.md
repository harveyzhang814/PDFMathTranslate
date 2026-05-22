# 导出为 Markdown

将翻译后的 PDF 导出为适合在 Obsidian 中使用的 Markdown 文档。

## 基本用法

```bash
pdf2zh document.pdf --markdown -o ./output
```

`--markdown` 会自动启用元素提取（相当于同时传入 `--extract-elements`），无需单独指定。

## 输出结构

```
output/
├── document-mono.md      # Markdown 正文（含 wikilink 图片引用）
└── images/
    ├── figure-1-p1.png   # 裁剪出的图表
    ├── table-2-p2.png
    └── ...
```

图片以 Obsidian wikilink 格式嵌入：

```markdown
![[images/figure-1-p1.png]]
*图 1：实验结果对比*

---
```

每页之间用 `---` 分隔。

## 常用组合

指定翻译服务和目标语言：

```bash
pdf2zh document.pdf --markdown -s deepl -lo zh -o ./output
```

只翻译部分页面：

```bash
pdf2zh document.pdf --markdown -p 1-5 -o ./output
```

## 注意事项

- 生成的 Markdown 针对 **Obsidian** 优化，使用 `![[...]]` 格式引用图片；在标准 Markdown 渲染器中图片将无法显示，需手动改为 `![](images/...)` 格式。
- 图片均裁剪自翻译后的单语 PDF，位置与原文一致。
- `--markdown` 和 `--word` 不能同时使用；如需两种格式，分两次运行。
