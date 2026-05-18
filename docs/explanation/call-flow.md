# 场景调用链与模块依赖关系

> 本文以实际运行场景为主线，逐条梳理真实调用顺序和模块依赖，并标注当前架构中的隐性耦合点。

---

## 一、进程启动序列（所有场景共享）

无论哪种接入方式，进程启动时都会先执行这段序列：

```
main() in pdf2zh.py
  │
  ├─ 1. ConfigManager.custome_config()   [M8] 加载用户配置文件（若有 --config）
  │
  ├─ 2. set_backend(parsed_args.backend) [M1] 配置 ONNX 推理设备（CPU/CUDA/DML）
  │
  └─ 3. ModelInstance.value = OnnxModel.load_available()  [M1] 加载版面检测模型
         │
         └─ 从 HuggingFace Hub 下载 ONNX 权重（首次运行）
            或读取本地缓存
```

**关键特征**：M1（版面模型）在启动时全局加载一次，后续以参数形式注入各翻译函数——这是整个项目里唯一做到依赖注入的地方。

---

## 二、场景一：CLI 普通翻译（`pdf2zh doc.pdf -s google`）

### 完整调用链

```
main()
  │
  ├─ [M6] KernelRegistry.switch("fast")
  ├─ [M6] kernel = KernelRegistry.get()          → LegacyKernel
  │
  ├─ 构建 TranslateRequest(files, lang_in, lang_out, service, ...)
  │
  └─ kernel.translate(request)
       │ LegacyKernel.translate()
       │
       └─ [M3] high_level.translate(files, ...)
              │
              ├─ check_files()                    文件存在性校验
              │
              ├─ [M4] is_convertible(file)?
              │         └─ convert_to_pdf(file)   .doc/.docx → 临时 PDF
              │
              ├─ open(file).read()                读取 PDF 字节
              │
              └─ [M3] translate_stream(bytes, ...)
                       │
                       ├─ download_remote_fonts(lang_out)   下载目标语言字体
                       │    └─ babeldoc.assets / HuggingFace Hub
                       │
                       ├─ pymupdf.Document(stream)          打开 PDF，注入字体
                       │
                       └─ [M3] translate_patch(fp, ...)
                                │
                                │  ◄─── 以下为逐页循环 ───►
                                │
                                ├─ doc_zh[pageno].get_pixmap()         渲染页面为像素图
                                │
                                ├─ [M1] model.predict(image)           版面检测
                                │         └─ 返回 figure/table/caption/abandon/... 区域框
                                │
                                ├─ 构建 layout[h×w] 像素掩码           标注"禁译区"
                                │    (abandon/figure/table → class=0)
                                │
                                ├─ [M3] interpreter.process_page(page)
                                │    │  PDFPageInterpreterEx
                                │    │    拦截 PDF 指令流（路径/XObject/颜色）
                                │    │
                                │    └─ [M3] TranslateConverter.receive_layout()
                                │               │
                                │               ├─ 遍历 LTChar，查 layout 掩码
                                │               │    公式字符 → 占位符 {vN}
                                │               │
                                │               ├─ 合并字符→段落
                                │               │
                                │               └─ ThreadPoolExecutor（并发翻译）
                                │                    └─ [M2] translator.translate(paragraph)
                                │                              │
                                │                              ├─ [M8] cache.get()  命中则直接返回
                                │                              ├─ 调用翻译服务 API
                                │                              └─ [M8] cache.set()  写入缓存
                                │
                                │  ◄─── 页面循环结束 ───►
                                │
                                └─ 返回 obj_patch（新 PDF 指令流字典）
                       │
                       ├─ 将 obj_patch 写回 doc_zh（更新 PDF 流）
                       ├─ doc_en.insert_file(doc_zh)  拼装双语 PDF
                       └─ 返回 (mono_bytes, dual_bytes)
              │
              ├─ 写 {filename}-mono.pdf
              └─ 写 {filename}-dual.pdf
```

### 模块调用顺序

```
启动时：  M8 → M1
运行时：  M6 → M3(translate) → M4? → M3(stream) → M3(patch) → M1(predict) → M3(interp) → M2 → M8
```

---

## 三、场景二：Word 导出（`pdf2zh doc.pdf --word`）

### 与场景一的关键差异

`--word` 标志在 `main()` 里被**提前拦截**，**完全绕过 Kernel 层（M6）**，直接调用 `translate_to_word()`。

```
main()
  │
  ├─ KernelRegistry.switch(...)   ← 仍然执行，但后续 kernel.translate() 不会被调用
  │
  └─ [parse_args.word == True]
       │
       └─ [M3] translate_to_word(files, ...)      ← 直接调用，跳过 M6
                │
                │  ── Step 1: 翻译（含元素提取）──
                │
                ├─ [M3] translate(files, extract_elements=True, elements_output_dir=elem_dir)
                │         │
                │         └─ translate_stream → translate_patch
                │                  │
                │                  │  页面循环中（额外逻辑）:
                │                  │
                │                  ├─ [M1] model.predict()         同场景一
                │                  │
                │                  ├─ 收集 figure_boxes / caption_boxes
                │                  │
                │                  ├─ [extract_elements=True]
                │                  │    └─ PIL.Image 裁剪图片区域
                │                  │         保存 p{N}_figure_{idx}.png
                │                  │         保存 p{N}_table_{idx}.png
                │                  │         → 写入 elem_dir/elements/
                │                  │
                │                  ├─ [M3] interpreter → converter → [M2] translate()
                │                  │
                │                  └─ 所有页处理完后:
                │                       ├─ 写 figures.json（图片页面坐标）
                │                       └─ [M5] pair_figure_caption()
                │                              build_element_manifest()
                │                              → 写 manifest.json
                │
                │  ── Step 2: Word 组装 ──
                │
                └─ [M5] export_pdf_to_word(mono_pdf, elem_dir, docx_path)
                          │
                          ├─ pymupdf 读取 mono.pdf 文字块（带坐标）
                          │
                          ├─ [M5] sort_text_blocks_by_layout()
                          │         └─ detect_column_layout()   单/双栏判断
                          │              sort by column + y 坐标
                          │
                          ├─ 遍历排序后文字块:
                          │    ├─ 检测标题（正则匹配 Figure/Table/图/表）
                          │    ├─ 检测是否有对应图片（查 manifest + figures.json）
                          │    ├─ _add_image_to_doc()
                          │    ├─ _add_caption_para()
                          │    └─ _add_body_para()
                          │
                          └─ doc.save(docx_path)
```

### 模块调用顺序

```
启动时：  M8 → M1
运行时：  M3(word) → M3(translate) → M4? → M3(stream+patch) → M1 → M3(interp) → M2 → M8
                                                                                  ↓
                                                                     M5(pair+manifest)
          → M5(export_word) → M5(text_order)
```

### 关键耦合观察

> **图片裁剪逻辑（PIL.Image 操作）嵌在 `translate_patch()` 内部**，与页面翻译循环混在一起，而不是在 M5 的 `export_pdf_to_word()` 中。这使得"翻译"和"元素提取"在代码层面是强耦合的。

---

## 四、场景三：GUI 模式（`pdf2zh --gui`）

```
main()
  └─ setup_gui()                     [M7/gui.py]
       │
       └─ Gradio app 启动，监听文件上传
            │
            └─ 用户上传 PDF，点击翻译
                 │
                 └─ [M3] high_level.translate()   ← 直接调用，跳过 M6
                          │
                          └─ 同场景一的 translate_stream → translate_patch 链路
```

**绕过**：M6（Kernel 层）

**特殊点**：GUI 使用 `_LazyModel` 包装器延迟加载模型（避免 Gradio 启动卡顿），但最终调用的是同一个 `OnnxModel`。进度回调通过 Gradio 的 `gr.Progress()` 传入 `translate()` 的 `callback` 参数。

---

## 五、场景四：REST API（`pdf2zh --flask`）

```
main()
  └─ flask_app.run(port=11008)
       │
       └─ POST /v1/translate
            │
            └─ celery_app.send_task("translate_task", args=[params])
                 │
                 └─ [异步 Worker] translate_task.run()
                       │
                       └─ [M3] translate_stream(stream_bytes, ...)  ← 直接调用，跳过 M6
                                │
                                └─ 同场景一的 translate_patch 链路
```

**绕过**：M6（Kernel 层），M4（不处理 .doc/.docx，直接收 PDF 字节流）

**特殊点**：这是唯一真正异步的接入方式。任务 ID 通过 `GET /v1/translate/<id>` 轮询状态，结果通过 `GET /v1/translate/<id>/mono` 下载。

---

## 六、场景五：MCP 工具调用（`pdf2zh --mcp`）

```
main()
  └─ create_mcp_app()                 [M7/mcp_server.py]
       │
       └─ MCP 服务器监听
            │
            └─ LLM 调用 translate_pdf 工具
                 │
                 ├─ [M4?] is_convertible()?  convert_to_pdf()
                 │
                 └─ [M3] translate_stream(pdf_bytes, ...)   ← 直接调用，跳过 M6
                          │
                          └─ 同场景一的 translate_patch 链路
```

**绕过**：M6（Kernel 层）

---

## 七、各场景 Kernel 使用情况汇总

| 场景 | 经过 M6 Kernel | 经过 M4 格式转换 | Word 导出 |
|---|:---:|:---:|:---:|
| CLI 普通翻译 | ✅ | ✅（translate内部） | ✗ |
| CLI Word 导出（--word）| ✗ 绕过 | ✅（translate内部） | ✅ |
| GUI | ✗ 绕过 | ✅（translate内部） | ✗ |
| REST API | ✗ 绕过 | ✗（仅接受字节流）| ✗ |
| MCP | ✗ 绕过 | ✅（mcp_server内） | ✗ |

> **结论**：M6（Kernel 调度层）实际上只在 CLI 普通翻译时生效。其余四种接入方式都直接调用了 `high_level` 的函数，Kernel 的协议抽象形同虚设。

---

## 八、核心依赖时序图

### 单页翻译的实际时序

```
translate_patch()
    │
    ▼
get_pixmap()             ~10ms  渲染页面像素图
    │
    ▼
model.predict()          ~200ms [M1] ONNX 推理（CPU），GPU 约 20ms
    │
    ▼
build layout[h×w]        ~5ms   构建像素掩码
    │
    ▼
interpreter.process_page()       [M3] 解析 PDF 指令流
    └─► receive_layout()
             │
             ├─ 字符分析 + 段落识别    ~5ms
             │
             └─ ThreadPoolExecutor
                  ├─ translator[0].translate()   [M2]
                  │    ├─ cache.get()    [M8]  命中→立即返回
                  │    └─ API 调用      200ms~3s（网络）
                  ├─ translator[1].translate()   [M2]
                  └─ ...（并发执行）
    │
    ▼
（Word 路径额外）
PIL.Image 裁剪+保存      ~20ms/图
pair_figure_caption()    ~1ms   [M5]
build_element_manifest() ~1ms   [M5]
```

**性能瓶颈**：翻译 API 调用（M2）是绝对瓶颈，`thread` 参数控制并发数直接决定吞吐量。M1 推理在 CPU 上是第二瓶颈（~200ms/页）。

---

## 九、隐性耦合点与风险

### 耦合点 1：Word 路径绕过 Kernel

**位置**：`pdf2zh.py:374`

```python
if parsed_args.word:
    from pdf2zh.high_level import translate_to_word
    ...
    translate_to_word(...)   # ← 不走 kernel，直接调
    return 0
```

**风险**：Precise 模式（v2 Kernel）对 `--word` 无效，用户无感知。未来若 v2 支持元素提取，这里需要单独适配。

---

### 耦合点 2：图片裁剪嵌在翻译循环内

**位置**：`high_level.py:190–215`（`translate_patch` 内部）

```python
if extract_elements and elements_output_dir:
    from PIL import Image
    ...
    pil_img.save(os.path.join(elem_dir, fname))   # ← M5 的职责混入了 M3
```

**风险**：翻译和元素提取现在是原子操作，无法单独重跑元素提取（例如调整裁剪参数时需重新翻译整个文档）。

---

### 耦合点 3：`converter.py` 顶层 import 全部 Translator

**位置**：`converter.py:13–38`

```python
from pdf2zh.translator import (
    AnythingLLMTranslator, ArgosTranslator, AzureOpenAITranslator, ...  # 25 个
)
```

**风险**：import `converter` 时会触发所有 SDK 的加载（openai、deepl、tencentcloud 等），即使用户只用 Google 翻译。增加启动时间，且任一 SDK 安装失败会导致整个模块不可用。

---

### 耦合点 4：GUI / MCP / API 不走 Kernel，配置不统一

**位置**：各接入层直接调用 `translate()` / `translate_stream()`

**风险**：`KernelRegistry.switch()` 对这些路径不生效。未来若要在 GUI 里切换 Fast/Precise 模式，需要在 `gui.py` 里单独实现路由逻辑，而不是复用 Kernel 系统。

---

## 十、建议优先修复的依赖顺序

若要改善解耦，建议按以下顺序推进（每步风险可控）：

```
Step 1  converter.py 改懒加载 Translator
        → 消除耦合点 3，降低启动开销和脆弱性

Step 2  将图片裁剪逻辑从 translate_patch() 移入 export_word.py
        → 消除耦合点 2，M3 和 M5 真正分离

Step 3  GUI / MCP / API 改走 KernelRegistry
        → 消除耦合点 4，统一路由逻辑

Step 4  --word 路径改走 Kernel，Kernel 协议扩展支持 Word 输出
        → 消除耦合点 1，Precise 模式可支持 Word 导出
```
