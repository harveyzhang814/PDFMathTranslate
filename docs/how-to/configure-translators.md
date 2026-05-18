# 配置翻译服务

## 指定服务

用 `-s` 标志指定服务名，可选择同时指定模型：

```bash
pdf2zh example.pdf -s google          # 使用 Google 翻译
pdf2zh example.pdf -s openai          # 使用环境变量中的模型
pdf2zh example.pdf -s openai:gpt-4o   # 直接指定模型
```

服务名与环境变量的完整列表见 [CLI 参考 → 翻译服务](../reference/cli.md#翻译服务与环境变量)。

---

## 通过环境变量配置

在命令前设置环境变量，或写入 shell profile：

```bash
# Linux / macOS
export OPENAI_API_KEY=sk-xxx
export OPENAI_MODEL=gpt-4o-mini
pdf2zh example.pdf -s openai

# Windows PowerShell
$env:OPENAI_API_KEY = "sk-xxx"
pdf2zh example.pdf -s openai
```

---

## 通过配置文件配置（推荐）

配置文件默认路径：`~/.config/PDFMathTranslate/config.json`

```bash
# 使用默认路径
pdf2zh example.pdf -s openai

# 使用自定义配置文件
pdf2zh example.pdf --config /path/to/config.json
```

配置文件示例（同时配置多个服务）：

```json
{
    "PDF2ZH_LANG_FROM": "English",
    "PDF2ZH_LANG_TO": "Simplified Chinese",
    "translators": [
        {
            "name": "openai",
            "envs": {
                "OPENAI_BASE_URL": "https://api.openai.com/v1",
                "OPENAI_API_KEY": "your-key",
                "OPENAI_MODEL": "gpt-4o-mini"
            }
        },
        {
            "name": "deepl",
            "envs": {
                "DEEPL_AUTH_KEY": "your-key"
            }
        },
        {
            "name": "ollama",
            "envs": {
                "OLLAMA_HOST": "http://127.0.0.1:11434",
                "OLLAMA_MODEL": "gemma2"
            }
        }
    ]
}
```

> 配置文件先于环境变量读取；环境变量存在时优先级更高，并会回写到配置文件。

---

## 使用 OpenAI 兼容代理

对于 Grok、本地代理等兼容 OpenAI API 的服务，使用 `grok` 或 `openailiked` 服务名：

```json
{
    "translators": [
        {
            "name": "grok",
            "envs": {
                "GROK_BASE_URL": "https://api.x.ai/v1",
                "GROK_API_KEY": "your-key",
                "GROK_MODEL": "grok-2-1212",
                "GROK_STREAM": "true"
            }
        }
    ]
}
```

不支持流式响应的代理：将 `*_STREAM` 设置为 `"false"`。

> `BASE_URL` 必须以 `/v1` 结尾，否则会返回 404 或 "Model not found" 错误。

---

## 自定义翻译提示词

仅适用于 LLM 类服务（OpenAI、Ollama 等）。

```bash
pdf2zh example.pdf -s openai --prompt prompt.txt
```

提示词文件示例（`prompt.txt`）：

```
You are a professional translation engine. Only output the translated text.

Translate the following markdown text to ${lang_out}. Keep formula notation {v*} unchanged.

Source Text: ${text}

Translated Text:
```

可用变量：

| 变量 | 含义 |
|------|------|
| `${lang_in}` | 源语言 |
| `${lang_out}` | 目标语言 |
| `${text}` | 待翻译文本 |

> 当前不支持 system prompt。
