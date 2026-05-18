# Python API 参考

> **注意**：当前 API 暂时弃用（相关代码不会移除，但不提供技术支持，也不修复 bug）。计划在 pdf2zh 2.0 发布后重新提供。需要程序化访问的用户，建议使用 [BabelDOC](https://github.com/funstory-ai/BabelDOC) 的 `babeldoc.high_level.async_translate`。

---

## 安装

```bash
pip install pdf2zh
```

## 接口

### `translate(files, **params) -> list`

按文件路径翻译，返回每个文件的 `(mono_path, dual_path)` 元组列表。

```python
from pdf2zh import translate

params = {
    'lang_in': 'en',
    'lang_out': 'zh',
    'service': 'google',
    'thread': 4,
}

results = translate(files=['example.pdf'], **params)
file_mono, file_dual = results[0]
```

### `translate_stream(stream, **params) -> tuple`

接受 PDF 字节流，返回 `(mono_bytes, dual_bytes)`。

```python
from pdf2zh import translate_stream

with open('example.pdf', 'rb') as f:
    stream_mono, stream_dual = translate_stream(stream=f.read(), **params)
```

## 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `lang_in` | `str` | 源语言代码（如 `"en"`） |
| `lang_out` | `str` | 目标语言代码（如 `"zh"`） |
| `service` | `str` | 翻译服务名，见 [CLI 参考](cli.md#翻译服务与环境变量) |
| `thread` | `int` | 并发翻译线程数 |
| `pages` | `list[int]` | 指定页码列表（0-indexed），不填则翻译全部 |
