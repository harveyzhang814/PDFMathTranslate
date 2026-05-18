# 作为 MCP 工具使用

PDFMathTranslate 可以作为 MCP（Model Context Protocol）服务器运行，让 Claude Desktop 等 AI 助手直接调用翻译能力。

## 安装

```bash
uv pip install pdf2zh
```

## 配置 Claude Desktop

编辑 `claude_desktop_config.json`，添加以下配置：

```json
{
    "mcpServers": {
        "filesystem": {
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                "/path/to/your/Documents"
            ]
        },
        "translate_pdf": {
            "command": "uv",
            "args": [
                "run",
                "pdf2zh",
                "--mcp"
            ]
        }
    }
}
```

`filesystem` 是必需的 MCP 服务器，用于让 AI 助手找到 PDF 文件；`translate_pdf` 是翻译服务器。

## 使用

配置完成后，在 Claude Desktop 中直接用自然语言指令：

```
找到我的 Documents 文件夹里的 paper.pdf，把它翻译成中文
```

## 手动启动服务器

```bash
pdf2zh --mcp
```
