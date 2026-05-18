# docs/ 文档索引

## how-to/ — 操作指南

完成具体任务的最短路径，不含原理解释。

| 文件 | 用途 |
|------|------|
| [how-to/install.md](how-to/install.md) | 5 种安装方式：uv、pip、exe、GUI、Docker；含 HF 镜像配置 |
| [how-to/configure-translators.md](how-to/configure-translators.md) | 配置翻译服务：env var、config.json、OpenAI 兼容代理、自定义提示词 |
| [how-to/use-mcp.md](how-to/use-mcp.md) | 作为 MCP 工具接入 Claude Desktop |
| [how-to/deploy-public-service.md](how-to/deploy-public-service.md) | 部署为公共服务：Docker、限制服务、隐藏 Key、GUI 授权 |
| [how-to/use-http-api.md](how-to/use-http-api.md) | 通过 HTTP API 提交翻译任务、查询进度、下载结果 |

## reference/ — 参考文档

稳定的事实、规范与 API 定义，供查阅。

| 文件 | 用途 |
|------|------|
| [reference/cli.md](reference/cli.md) | 所有 CLI 选项、25 种翻译服务的环境变量表、config.json 格式 |
| [reference/python-api.md](reference/python-api.md) | Python API：`translate()` 和 `translate_stream()` 签名与参数 |

## explanation/ — 理解类

架构背景与设计原理，供开发者理解系统。

| 文件 | 用途 |
|------|------|
| [explanation/call-flow.md](explanation/call-flow.md) | 5 种接入场景的完整调用链；Kernel 绕过汇总；4 个隐性耦合点分析 |
| [explanation/module-architecture.md](explanation/module-architecture.md) | M1–M8 模块边界、依赖矩阵、解耦就绪度评分与三批次重构路线 |

## rfcs/ — 设计提案

尚未实现的功能设计，状态为「待实现」。

| 文件 | 用途 |
|------|------|
| [rfcs/2026-05-18-markdown-export-design.md](rfcs/2026-05-18-markdown-export-design.md) | Markdown 导出（`--markdown`）功能的完整设计 spec |
