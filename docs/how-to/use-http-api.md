# 使用 HTTP API

> **注意**：HTTP API 暂时弃用，不提供技术支持。相关代码保留但不修复 bug。

## 启动服务

```bash
pip install pdf2zh[backend]
pdf2zh --flask
pdf2zh --celery worker
```

服务监听在 `http://localhost:11008`。

---

## API 端点

### 提交翻译任务

```bash
curl http://localhost:11008/v1/translate \
  -F "file=@example.pdf" \
  -F 'data={"lang_in":"en","lang_out":"zh","service":"google","thread":4}'
```

响应：

```json
{"id": "d9894125-2f4e-45ea-9d93-1a9068d2045a"}
```

### 查询进度

```bash
curl http://localhost:11008/v1/translate/d9894125-2f4e-45ea-9d93-1a9068d2045a
```

进行中：

```json
{"info": {"n": 13, "total": 506}, "state": "PROGRESS"}
```

已完成：

```json
{"state": "SUCCESS"}
```

### 下载结果

```bash
# 单语译文
curl http://localhost:11008/v1/translate/d9894125-2f4e-45ea-9d93-1a9068d2045a/mono \
  --output example-mono.pdf

# 双语对照
curl http://localhost:11008/v1/translate/d9894125-2f4e-45ea-9d93-1a9068d2045a/dual \
  --output example-dual.pdf
```

### 取消并删除任务

```bash
curl -X DELETE http://localhost:11008/v1/translate/d9894125-2f4e-45ea-9d93-1a9068d2045a
```
