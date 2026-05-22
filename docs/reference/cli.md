# CLI 参考

## 命令行选项

| 选项 | 功能 | 示例 |
|------|------|------|
| `files` | 本地文件 | `pdf2zh ~/local.pdf` |
| `links` | 在线文件 | `pdf2zh http://arxiv.org/paper.pdf` |
| `-i` | 启动图形界面 | `pdf2zh -i` |
| `-p` | 部分页面翻译 | `pdf2zh example.pdf -p 1-3,5` |
| `-li` | 源语言 | `pdf2zh example.pdf -li en` |
| `-lo` | 目标语言 | `pdf2zh example.pdf -lo zh` |
| `-s` | 翻译服务 | `pdf2zh example.pdf -s deepl` |
| `-t` | 并发线程数 | `pdf2zh example.pdf -t 4` |
| `-o` | 输出目录 | `pdf2zh example.pdf -o output` |
| `-f` | 保护字体（正则） | `pdf2zh example.pdf -f "(MS.*)"` |
| `-c` | 保护字符（正则） | `pdf2zh example.pdf -c "(\d)"` |
| `-cp` | 兼容模式 | `pdf2zh example.pdf --compatible` |
| `--share` | Gradio 公开链接 | `pdf2zh -i --share` |
| `--authorized` | GUI 授权文件 | `pdf2zh -i --authorized users.txt auth.html` |
| `--prompt` | 自定义翻译提示词 | `pdf2zh --prompt prompt.txt` |
| `--onnx` | 自定义 DocLayout-YOLO ONNX 模型路径 | `pdf2zh --onnx /path/model.onnx` |
| `--serverport` | 自定义 WebUI 端口 | `pdf2zh --serverport 7860` |
| `--dir` | 批量翻译目录 | `pdf2zh --dir /path/to/pdfs/` |
| `--config` | 配置文件路径 | `pdf2zh --config config.json` |
| `--mode` | 翻译内核：`fast`（默认）或 `precise`（实验性） | `pdf2zh --mode precise example.pdf` |
| `--extract-elements` | 提取图表为独立图片文件（由 `--word` / `--markdown` 自动启用，也可单独使用） | `pdf2zh example.pdf --extract-elements` |
| `--word` | 导出为 Word 文档（自动启用 `--extract-elements`；与 `--markdown` 互斥） | `pdf2zh example.pdf --word` |
| `--markdown` | 导出为 Markdown（图片置于 `images/`，Obsidian wikilink 格式；自动启用 `--extract-elements`；与 `--word` 互斥） | `pdf2zh example.pdf --markdown` |
| `--no-pdf` | 配合 `--word` 使用，丢弃中间 PDF 只保留 `.docx` | `pdf2zh example.pdf --word --no-pdf` |
| `--skip-subset-fonts` | 禁用字体子集化 | `pdf2zh example.pdf --skip-subset-fonts` |
| `--ignore-cache` | 忽略翻译缓存，强制重新翻译 | `pdf2zh example.pdf --ignore-cache` |

语言代码参考：[Google 语言代码](https://developers.google.com/admin-sdk/directory/v1/languages)、[DeepL 语言代码](https://developers.deepl.com/docs/resources/supported-languages)

---

## 参数依赖关系

| 参数 | 自动启用 | 与以下参数互斥 |
|------|---------|--------------|
| `--word` | `--extract-elements` | `--markdown` |
| `--markdown` | `--extract-elements` | `--word` |
| `--extract-elements` | — | — |

依赖关系由 `pdf2zh/pdf2zh.py` 中的 `ARG_IMPLIES` 字典在 `parse_args()` 阶段统一解析；互斥约束由 argparse `mutually_exclusive_group` 强制执行（传入互斥参数会立即报错）。

---

## 翻译服务与环境变量

使用 `-s service` 或 `-s service:model` 指定服务：

```bash
pdf2zh example.pdf -s openai:gpt-4o-mini
```

| 服务名 | `-s` 参数 | 环境变量 | 默认值 |
|--------|----------|---------|-------|
| Google（默认） | `google` | — | — |
| Bing | `bing` | — | — |
| 302.AI | `302ai` | `X302AI_API_KEY`, `X302AI_MODEL` | `Gemma-7B` |
| OpenAI | `openai` | `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_STOP_TOKENS`, `OPENAI_MAX_TOKENS` | `https://api.openai.com/v1`, `gpt-4o-mini`, ` `, `-1` |
| DeepL | `deepl` | `DEEPL_AUTH_KEY` | — |
| DeepLX | `deeplx` | `DEEPLX_ENDPOINT` | `https://api.deepl.com/translate` |
| Ollama | `ollama` | `OLLAMA_HOST`, `OLLAMA_MODEL` | `http://127.0.0.1:11434`, `gemma2` |
| Xinference | `xinference` | `XINFERENCE_HOST`, `XINFERENCE_MODEL` | `http://127.0.0.1:9997`, `gemma-2-it` |
| Azure OpenAI | `azure-openai` | `AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_MODEL` | `gpt-4o-mini` |
| 智谱 | `zhipu` | `ZHIPU_API_KEY`, `ZHIPU_MODEL` | `glm-4-flash` |
| ModelScope | `modelscope` | `MODELSCOPE_API_KEY`, `MODELSCOPE_MODEL` | `Qwen/Qwen2.5-Coder-32B-Instruct` |
| Silicon | `silicon` | `SILICON_API_KEY`, `SILICON_MODEL` | `Qwen/Qwen2.5-7B-Instruct` |
| Gemini | `gemini` | `GEMINI_API_KEY`, `GEMINI_MODEL` | `gemini-1.5-flash` |
| Azure | `azure` | `AZURE_ENDPOINT`, `AZURE_API_KEY` | `https://api.translator.azure.cn` |
| Tencent | `tencent` | `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY` | — |
| Dify | `dify` | `DIFY_API_URL`, `DIFY_API_KEY` | — |
| AnythingLLM | `anythingllm` | `AnythingLLM_URL`, `AnythingLLM_APIKEY` | — |
| Argos Translate | `argos` | — | — |
| Grok | `grok` | `GROK_API_KEY`, `GROK_MODEL`, `GROK_BASE_URL`（可选） | `grok-2-1212`, `https://api.x.ai/v1` |
| Groq | `groq` | `GROQ_API_KEY`, `GROQ_MODEL` | `llama-3-3-70b-versatile` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL` | `deepseek-chat` |
| MiniMax | `minimax` | `MINIMAX_API_KEY`, `MINIMAX_MODEL` | `MiniMax-M2.7` |
| OpenAI-兼容 | `openailiked` | `OPENAILIKED_BASE_URL`, `OPENAILIKED_API_KEY`, `OPENAILIKED_MODEL`, `OPENAILIKED_STOP_TOKENS`, `OPENAILIKED_MAX_TOKENS` | ` `, `-1` |
| 阿里通义翻译 | `qwen-mt` | `ALI_MODEL`, `ALI_API_KEY`, `ALI_DOMAINS` | `qwen-mt-turbo`, `scientific paper` |

> 凡兼容 OpenAI API 但未列入上表的模型，均可使用 `openailiked` 服务，配置方法与 OpenAI 相同。

---

## 公式/字体保护正则

默认保护的字体（`-f`）：

```
(CM[^R]|MS.M|XY|MT|BL|RM|EU|LA|RS|LINE|LCIRCLE|TeX-|rsfs|txsy|wasy|stmary|.*Mono|.*Code|.*Ital|.*Sym|.*Math)
```

示例——同时指定字体和字符保护：

```bash
pdf2zh example.pdf -f "(CM[^RT].*|MS.*|.*Ital)" -c "(\(|\||\)|\+|=|\d|[-﫿])"
```

---

## 配置文件格式（config.json）

默认路径：`~/.config/PDFMathTranslate/config.json`

启动时先读配置文件，再读环境变量；环境变量优先级更高。

```json
{
    "USE_MODELSCOPE": "0",
    "PDF2ZH_LANG_FROM": "English",
    "PDF2ZH_LANG_TO": "Simplified Chinese",
    "NOTO_FONT_PATH": "/app/SourceHanSerifCN-Regular.ttf",
    "translators": [
        {
            "name": "openai",
            "envs": {
                "OPENAI_BASE_URL": "https://api.openai.com/v1",
                "OPENAI_API_KEY": "your-api-key",
                "OPENAI_MODEL": "gpt-4o-mini"
            }
        }
    ]
}
```

> **注意**：使用 OpenAI 兼容代理时，`BASE_URL` 必须以 `/v1` 结尾，否则会返回 404。

公共服务部署时可额外设置：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ENABLED_SERVICES` | `string[]` | 只开放指定翻译服务，其余隐藏 |
| `HIDDEN_GRADIO_DETAILS` | `bool` | 在 Web UI 隐藏真实 API Key |
