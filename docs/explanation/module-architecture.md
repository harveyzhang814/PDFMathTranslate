# 模块架构：可解耦颗粒度分析

> 本文从产品功能边界出发，按"最小可替换单元"拆分模块，识别当前耦合点与解耦路径。

---

## 总体模块地图

```
┌─────────────────────────────────────────────────────────────────┐
│                        M7 · 接入层                              │
│   CLI (pdf2zh.py) │ GUI (gui.py) │ API (backend.py) │ MCP      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ TranslateRequest / TranslateResult
┌──────────────────────────▼──────────────────────────────────────┐
│                    M6 · Kernel 调度层                            │
│          KernelRegistry → LegacyKernel / PreciseKernel          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
          ┌────────────────┴────────────────┐
          │                                 │
┌─────────▼──────────┐           ┌──────────▼──────────────────┐
│  M3 · PDF 翻译引擎  │           │  M5 · Word 导出管道          │
│  high_level.py     │           │  export_word.py              │
│  converter.py      │           │  text_order.py               │
│  pdfinterp.py      │           │  caption_pairing.py          │
└──┬──────┬──────────┘           └─────────────────────────────┘
   │      │
   │   ┌──▼──────────────────┐
   │   │  M1 · 版面检测       │
   │   │  doclayout.py       │
   │   └─────────────────────┘
   │
┌──▼──────────────────────────┐
│  M2 · 翻译服务枢纽           │
│  translator.py               │
│  cache.py                    │
└──────────────┬───────────────┘
               │
┌──────────────▼───────────────┐
│  M8 · 基础设施               │
│  config.py                   │
└──────────────────────────────┘

M4 · 格式预处理 (converter_docx.py) ──► M3
```

---

## 各模块详述

---

### M1 · 版面检测模块

**对应文件**：`pdf2zh/doclayout.py`

**职责**：接收页面图像，用 YOLO-ONNX 模型识别各区域类型（figure / table / caption / formula / abandon / text），返回带坐标的检测结果。

**接口**

| 方向 | 内容 |
|---|---|
| 输入 | numpy 数组（页面像素图），推理设备配置 |
| 输出 | `List[YoloBox]`，每项含 `(x0, y0, x1, y1, class_id, confidence)` |

**外部依赖**：`onnxruntime`、`opencv`、`numpy`、`huggingface_hub`（模型下载）

**内部依赖**：**零**——不引用项目其他模块

**解耦就绪度**：★★★★★ 可直接抽成独立包，接口天然清晰。

**当前耦合点**：`high_level.translate_patch()` 直接实例化 `OnnxModel`，`ModelInstance` 单例全局共享——需改为依赖注入。

---

### M2 · 翻译服务枢纽

**对应文件**：`pdf2zh/translator.py`、`pdf2zh/cache.py`

**职责**：统一 25 种翻译后端的调用接口，提供带参数哈希的 SQLite 缓存，屏蔽上游对具体服务商的感知。

**接口**

| 方向 | 内容 |
|---|---|
| 输入 | 原文字符串、源语言、目标语言、服务商名称、API 配置 |
| 输出 | 译文字符串 |

**外部依赖**：`openai`、`deepl`、`ollama`、`requests`、`azure-ai-translation-text`、`tencentcloud-sdk`、`peewee`（缓存 ORM）

**内部依赖**：`config.py`（读取 API Key）、`cache.py`（缓存读写）

**解耦就绪度**：★★★★☆ 接口语义清晰，但 `translator.py` 直接 import 了所有服务商 SDK（即使未使用）——需改为懒加载或插件注册。

**当前耦合点**：`converter.py` 在顶层 import 所有 25 个 Translator 类（第 13–38 行），导致启动时全量加载。

---

### M3 · PDF 翻译引擎

**对应文件**：`pdf2zh/high_level.py`、`pdf2zh/converter.py`、`pdf2zh/pdfinterp.py`

**职责**：这是核心差异化能力。逐页解析 PDF 内容流，识别并保护数学公式（基于字体名 + 字符类型双重规则），将正文段落送往翻译，最终重新生成合法 PDF 字节流。

**内部子结构**

```
high_level.translate_patch()         ← 编排者：逐页调度
    ├─ pdfinterp.PDFPageInterpreterEx ← 低层：拦截 PDF 指令流
    └─ converter.TranslateConverter   ← 核心：段落识别 + 公式保护 + 重排
           └─ translator.translate()  ← 多线程并发翻译
```

**接口**

| 方向 | 内容 |
|---|---|
| 输入 | PDF 二进制流、语言对、Translator 实例、版面检测结果（layout 数组）、页码范围 |
| 输出 | 单语译文 PDF 字节流（mono）、双语对照 PDF 字节流（dual） |

**外部依赖**：`pdfminer-six`、`pymupdf`、`babeldoc`（字体资产）

**内部依赖**：M1（版面检测）、M2（翻译服务）、M8（配置）

**解耦就绪度**：★★★☆☆ 功能边界清晰，但 `high_level.py` 同时承担了文件 I/O、字体下载、元素提取调度等职责，是当前耦合最重的位置。

**当前耦合点**：
- `high_level.translate()` 直接调用 `export_word.export_pdf_to_word()`，Word 导出逻辑与翻译主流程混在同一函数
- `translate_patch()` 内嵌图片裁剪和元素保存逻辑（本应属于 M5）

---

### M4 · 格式预处理模块

**对应文件**：`pdf2zh/converter_docx.py`

**职责**：将 `.doc` / `.docx` 文件通过 LibreOffice headless 转换为 PDF，作为 M3 的输入前置步骤。

**接口**

| 方向 | 内容 |
|---|---|
| 输入 | `.doc` / `.docx` 文件路径 |
| 输出 | 临时 PDF 文件路径 |

**外部依赖**：系统级 LibreOffice（运行时 shell 调用）

**内部依赖**：无

**解耦就绪度**：★★★★★ 完全独立，无内部依赖，可随时抽离。

**当前耦合点**：`high_level.translate()` 和 `mcp_server.py` 各自直接 import 此模块——可统一到接入层处理。

---

### M5 · Word 导出管道

**对应文件**：`pdf2zh/export_word.py`、`pdf2zh/text_order.py`、`pdf2zh/caption_pairing.py`

**职责**：消费翻译产物（mono.pdf + 元素图片），重建可编辑 Word 文档，保留版面结构（图文顺序、标题配对、双栏感知）。

**内部子结构**

```
export_pdf_to_word()
    ├─ caption_pairing.pair_figure_caption()     ← 图↔标题空间配对
    ├─ caption_pairing.build_element_manifest()  ← 写 manifest.json
    ├─ text_order.sort_text_blocks_by_layout()   ← 阅读顺序排序
    └─ python-docx 组装 .docx
```

**接口**

| 方向 | 内容 |
|---|---|
| 输入 | mono.pdf 路径、elements/ 目录（含裁剪图片）、输出目录 |
| 输出 | `.docx` 文件 |

**外部依赖**：`python-docx`、`pymupdf`、`numpy`

**内部依赖**：仅依赖 M3 的产物（文件路径），不调用 M3 代码

**解耦就绪度**：★★★★☆ 模块内部三个文件协作良好，对外接口是纯文件 I/O，天然解耦。

**当前耦合点**：`caption_pairing.py` 的图片裁剪触发时机在 `high_level.translate_patch()` 内部——元素提取逻辑与翻译流程还未完全分离。

---

### M6 · Kernel 调度层

**对应文件**：`pdf2zh/kernel/protocol.py`、`pdf2zh/kernel/registry.py`、`pdf2zh/kernel/legacy.py`、`pdf2zh/kernel/precise.py`、`pdf2zh/kernel/v2_bridge.py`、`pdf2zh/kernel/v2_worker.py`

**职责**：统一翻译请求的调度接口，允许在 Fast（v1 本地引擎）和 Precise（v2 隔离子进程）间热切换，对接入层屏蔽引擎差异。

**内部子结构**

```
KernelRegistry
    ├─ LegacyKernel   → high_level.translate()
    └─ PreciseKernel  → v2_bridge → subprocess → v2_worker → pdf2zh_next
```

**接口**

| 方向 | 内容 |
|---|---|
| 输入 | `TranslateRequest`（dataclass，含文件路径、语言对、服务商、页码范围等） |
| 输出 | `TranslateResult`（含输出文件路径、进度） |

**外部依赖**：无额外依赖（依赖 M3，但通过函数调用而非 SDK）

**内部依赖**：`LegacyKernel` → M3；`PreciseKernel` → 独立 venv（依赖隔离）

**解耦就绪度**：★★★★☆ `protocol.py` 已定义清晰协议，Registry 设计完整，可扩展新 Kernel。

**当前耦合点**：`LegacyKernel` 直接 import `high_level`——若 M3 重构需同步更新参数映射。

---

### M7 · 接入层

**对应文件**：`pdf2zh/pdf2zh.py`（CLI）、`pdf2zh/gui.py`（Web GUI）、`pdf2zh/backend.py`（REST API）、`pdf2zh/mcp_server.py`（MCP）

**职责**：各接入方式独立处理用户输入，统一转换为 `TranslateRequest` 交给 M6，展示结果。

**各接入点对比**

| 接入点 | 目标用户 | 异步支持 | 进度展示 |
|---|---|---|---|
| CLI | 开发者、脚本 | 否 | tqdm 进度条 |
| GUI | 非技术用户 | 否（阻塞） | Gradio 进度 |
| REST API | 集成方 | 是（Celery） | 轮询 `/v1/translate/<id>` |
| MCP | AI 助手 | 否 | 无（工具调用） |

**解耦就绪度**：★★★☆☆ 各接入点之间互不依赖，但 `pdf2zh.py` 仍直接 import translator 类列表来构建 `--service` 参数选项，与 M2 存在列表级耦合。

---

### M8 · 基础设施层

**对应文件**：`pdf2zh/config.py`、`pdf2zh/cache.py`

**职责**：提供全局共享的配置读写和翻译结果缓存，供 M2、M3 使用。

**接口**

| 模块 | 接口 |
|---|---|
| `ConfigManager` | `get(key)` / `set(key, value)`，线程安全 RLock |
| `TranslationCache` | `get(text, params)` / `set(text, params, result)`，参数哈希命中 |

**外部依赖**：`peewee`（SQLite ORM）

**内部依赖**：无

**解耦就绪度**：★★★★★

---

## 模块依赖矩阵

```
         M1  M2  M3  M4  M5  M6  M7  M8
M1 版面   ·   ·   ·   ·   ·   ·   ·   ·    ← 无内部依赖
M2 翻译   ·   ·   ·   ·   ·   ·   ·   ▲    ← 依赖 M8(config/cache)
M3 引擎   ▲   ▲   ·   ·   ·   ·   ·   ▲    ← 依赖 M1, M2, M8
M4 预处理  ·   ·   ·   ·   ·   ·   ·   ·    ← 无内部依赖
M5 Word   ·   ·   ▲*  ·   ·   ·   ·   ·    ← 仅依赖 M3 产物(文件)
M6 调度   ·   ·   ▲   ·   ·   ·   ·   ·    ← 依赖 M3
M7 接入   ·   ▲*  ·   ▲   ·   ▲   ·   ·    ← 依赖 M2(列表), M4, M6
M8 基础   ·   ·   ·   ·   ·   ·   ·   ·    ← 无内部依赖

▲ 代码级依赖    ▲* 列表/配置级耦合（非调用）
```

---

## 解耦优先级建议

### 第一批：零成本解耦（接口已天然清晰）

| 优先级 | 模块 | 动作 |
|---|---|---|
| P0 | M1 版面检测 | 改为依赖注入，`OnnxModel` 实例由外部传入 `translate_patch()` |
| P0 | M4 格式预处理 | 移入接入层（M7）处理，不在 `high_level.py` 内调用 |
| P0 | M8 基础设施 | 已解耦，维持现状 |

### 第二批：边界梳理（需小重构）

| 优先级 | 模块 | 动作 |
|---|---|---|
| P1 | M5 Word 导出 | 将 `high_level.py` 内的图片裁剪/保存逻辑移入 M5 |
| P1 | M2 翻译服务 | 改为懒加载或插件注册，消除 `converter.py` 顶层 25 个 import |
| P1 | M7 接入层 | CLI `--service` 参数列表改从 registry 动态读取，不硬编码 |

### 第三批：架构升级（需较大改动）

| 优先级 | 模块 | 动作 |
|---|---|---|
| P2 | M3 翻译引擎 | 将 `high_level.py` 拆分为「文件 I/O 编排」和「PDF 流处理」两层 |
| P2 | M6 Kernel | 支持外部 Kernel 注册（插件化），打开扩展点 |

---

## 各模块解耦就绪度汇总

```
M1 版面检测    ████████████████████  100%  可立即抽包
M8 基础设施    ████████████████████  100%  已解耦
M4 格式预处理  ████████████████░░░░   80%  挪调用位置即可
M2 翻译服务    ████████████████░░░░   80%  改懒加载
M5 Word 导出   ████████████████░░░░   80%  移走裁图逻辑
M6 Kernel     ████████████░░░░░░░░   60%  协议已清晰，实现待插件化
M7 接入层     ████████████░░░░░░░░   60%  动态读取服务列表
M3 翻译引擎   ████████░░░░░░░░░░░░   40%  核心重，需拆编排与处理
```
