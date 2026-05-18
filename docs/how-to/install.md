# 安装 PDFMathTranslate

> 这是 [Byaidu/PDFMathTranslate](https://github.com/Byaidu/PDFMathTranslate) 的个人 fork，添加了元素提取、列布局排序和 Word 导出等实验性功能。稳定版请访问[上游仓库](https://github.com/Byaidu/PDFMathTranslate)。

## 方法一：uv 安装（推荐）

1. 安装 Python 3.11–3.12
2. 安装包：

   ```bash
   pip install uv
   uv tool install --python 3.12 pdf2zh
   ```

3. 验证安装：

   ```bash
   pdf2zh --version
   ```

## 方法二：pip 安装

```bash
pip install pdf2zh
```

## 方法三：Windows exe

1. 从 [Releases 页面](https://github.com/Byaidu/PDFMathTranslate/releases) 下载 `pdf2zh-version-win64.zip`
2. 解压后双击 `pdf2zh.exe`

> 如果无法打开，先安装 [vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe)

## 方法四：图形界面（GUI）

1. 安装 Python 3.11–3.12 并安装包：

   ```bash
   pip install pdf2zh
   ```

2. 启动 GUI：

   ```bash
   pdf2zh -i
   ```

3. 浏览器访问 `http://localhost:7860/`

## 方法五：Docker

```bash
docker pull byaidu/pdf2zh
docker run -d -p 7860:7860 byaidu/pdf2zh
```

浏览器访问 `http://localhost:7860/`

> 如果无法访问 Docker Hub，改用 GitHub Container Registry：
>
> ```bash
> docker pull ghcr.io/byaidu/pdfmathtranslate
> docker run -d -p 7860:7860 ghcr.io/byaidu/pdfmathtranslate
> ```

---

## 模型下载失败

首次运行需下载 ONNX 版面检测模型（`wybxc/DocLayout-YOLO-DocStructBench-onnx`）。网络受限时设置镜像：

```bash
# Linux / macOS
export HF_ENDPOINT=https://hf-mirror.com

# Windows CMD
set HF_ENDPOINT=https://hf-mirror.com

# PowerShell
$env:HF_ENDPOINT = "https://hf-mirror.com"
```
