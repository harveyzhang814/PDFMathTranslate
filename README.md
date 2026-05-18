<div align="center">

> **This is a personal fork of [Byaidu/PDFMathTranslate](https://github.com/Byaidu/PDFMathTranslate).**  
> It adds experimental features for element extraction, column-aware reading order, and Word document export.  
> For the stable release, please visit the [upstream repository](https://github.com/Byaidu/PDFMathTranslate).

</div>

<br>

<div align="center">

<img src="./docs/images/banner.png" width="320px"  alt="PDF2ZH"/>

<h2 id="title">PDFMathTranslate</h2>

<p>
  <a href="https://github.com/harveyzhang814/PDFMathTranslate/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/Byaidu/PDFMathTranslate"></a>
  <a href="https://github.com/harveyzhang814/PDFMathTranslate/issues">
    <img src="https://img.shields.io/badge/issues-welcome-green"></a>
</p>

</div>

<h2 id="updates">1. What does this do?</h2>

Scientific PDF document translation preserving layouts.

- 📊 Preserve formulas, charts, table of contents, and annotations.
- 🌐 Support [multiple languages](#usage), and diverse [translation services](#usage).
- 🤖 Provides [commandline tool](#usage), [interactive user interface](#install), and [Docker](#install)

<h3 id="fork-features">1.1 Features added in this fork</h3>

The following features are experimental additions on top of the upstream project:

| Feature | Description | Option / API |
| ------- | ----------- | ------------ |
| **Element extraction** | Extract figures and tables from the PDF as separate image files | `--extract-elements` |
| **Column-aware reading order** | Detect multi-column layouts and sort text blocks into the correct reading order before translation | automatic |
| **Figure caption pairing** | Associate figure captions with their corresponding figure boxes for improved context | automatic |
| **Word document export** | Export the translated result as a `.docx` file with embedded images and tables | `--word` |
| **Markdown export** | Export the translated result as a `.md` file with figures in an `images/` subfolder (Obsidian wikilink format) | `--markdown` |

<div align="center">
<img src="./docs/images/preview.gif" width="80%"/>
</div>

<h2 id="updates">2. Recent Updates</h2>

- [March 23, 2026] Experimental support for v2.0 translation kernel using isolated environment (`--mode precise`). (by [@reycn](https://github.com/reycn))
- [March 22, 2026] Supporting MiniMax (PR by [@octo-patch](https://github.com/octo-patch))
- [March 22, 2026] Fixing OpenAI-related issues (PR by [@samqin123](https://github.com/samqin123))
- [March 22, 2026] Fixing HTTP-related issues (PR by [@soukouki](https://github.com/soukouki))
- [March 22, 2026] Faster model loading on mac and OONX platforms, GUI starting-up, version printing, and continuous integration.(by [@reycn](https://github.com/reycn))
- [May 9, 2025] pdf2zh 2.0 Preview Version [#586](https://github.com/Byaidu/PDFMathTranslate/issues/586): The Windows ZIP file and Docker image are now available.

  > [!NOTE]
  >
  > 2.0 Moved to a new repository under the organization: [PDFMathTranslate/PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next)
  > 
  > Version 2.0 official release has been published.

<h2 id="use-section">3. Use 🌟</h2>
<h3 id="demo">3.1 Online Service 🌟</h3>

You can try our application out using either of the following demos:

- [Public free service](https://pdf2zh.com/) online without installation _(recommended)_.
- [Immersive Translate - BabelDOC](https://app.immersivetranslate.com/babel-doc/) Free usage quota is available; please refer to the FAQ section on the page for details. _(recommended)_
- [Demo hosted on HuggingFace](https://huggingface.co/spaces/reycn/PDFMathTranslate-Docker)
- [Demo hosted on ModelScope](https://www.modelscope.cn/studios/AI-ModelScope/PDFMathTranslate) without installation.

Note that the computing resources of the demo are limited, so please avoid abusing them.

<h3 id="install">3.2 Local Installation</h3>

For different use cases, we provide distinct methods to use our program:

<details open>
  <summary>3.2.1 Python: Install using uv</summary>

1. Python installed (3.11 <= version <= 3.12)

2. Install our package:

   ```bash
   pip install uv
   uv tool install --python 3.12 pdf2zh
   ```

3. Execute translation, files generated in [current working directory](https://chatgpt.com/share/6745ed36-9acc-800e-8a90-59204bd13444):

   ```bash
   pdf2zh document.pdf
   ```

</details>
<details>
  <summary>3.2.2 Python: Install using pip</summary>

1. Python installed (3.11 <= version <= 3.12)
2. Install our package:

   ```bash
   pip install pdf2zh
   ```

3. Execute translation, files generated in [current working directory](https://chatgpt.com/share/6745ed36-9acc-800e-8a90-59204bd13444):

   ```bash
   pdf2zh document.pdf
   ```

</details>
<details>
  <summary>3.3.3 Python: Graphic user interface</summary>

1. Python installed (3.11 <= version <= 3.12)

2. Install our package:

  ```bash
  pip install pdf2zh
  ```

3. Start using in browser:

   ```bash
   pdf2zh -i
   ```

4. If your browser has not been started automatically, goto

   ```bash
   http://localhost:7860/
   ```

   <img src="./docs/images/gui.gif" width="500"/>

See [documentation for GUI](./docs/README_GUI.md) for more details.

</details>

<details>
  <summary>3.2.4 Application: On Windows</summary>

1. Download pdf2zh-version-win64.zip from the [upstream release page](https://github.com/Byaidu/PDFMathTranslate/releases) (this fork does not publish Windows builds)

2. Unzip and double-click `pdf2zh.exe` to run.


  > [!TIP]
  >
  > - If you're using Windows and cannot open the file after downloading, please install [vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe) and try again.
  > 
</details>


<details>

<summary>3.2.5 Reference manager: Zotero Plugin</summary>


See [Zotero PDF2zh](https://github.com/guaguastandup/zotero-pdf2zh) for more details.

</details>


<details>
  <summary>3.2.6 Docker: Containerized Deployment</summary>

1. Pull and run (upstream stable image):

   ```bash
   docker pull byaidu/pdf2zh
   docker run -d -p 7860:7860 byaidu/pdf2zh
   ```

   > [!NOTE]
   > This fork does not publish its own Docker image. The command above pulls the upstream stable image. To run this fork, build locally: `docker build -t pdf2zh-fork .`

2. Open in browser:

   ```
   http://localhost:7860/
   ```

> [!NOTE]
> The one-click cloud deploy buttons below are provided by the upstream project and will deploy the **upstream** repository, not this fork. Use them for reference only.

<details>
<summary>Upstream one-click cloud deploy (deploys Byaidu/PDFMathTranslate, not this fork)</summary>
<div>
<a href="https://www.heroku.com/deploy?template=https://github.com/Byaidu/PDFMathTranslate">
  <img src="https://www.herokucdn.com/deploy/button.svg" alt="Deploy" height="26"></a>
<a href="https://render.com/deploy">
  <img src="https://render.com/images/deploy-to-render-button.svg" alt="Deploy to Koyeb" height="26"></a>
<a href="https://zeabur.com/templates/5FQIGX?referralCode=reycn">
  <img src="https://zeabur.com/button.svg" alt="Deploy on Zeabur" height="26"></a>
<a href="https://template.sealos.io/deploy?templateName=pdf2zh">
  <img src="https://sealos.io/Deploy-on-Sealos.svg" alt="Deploy on Sealos" height="26"></a>
<a href="https://app.koyeb.com/deploy?type=git&builder=buildpack&repository=github.com/Byaidu/PDFMathTranslate&branch=main&name=pdf-math-translate">
  <img src="https://www.koyeb.com/static/images/deploy/button.svg" alt="Deploy to Koyeb" height="26"></a>
</div>
</details>
</details>

<details>
  <summary>3.2.* Solutions for network issues in installation</summary>

  Users in specific regions may encounter network difficulties when loading the AI model. The current program relies on the AI model (`wybxc/DocLayout-YOLO-DocStructBench-onnx`), and some users are unable to download it due to these network issues.

  To address issues with downloading this model, use the following environment variable as a workaround:

  ```shell
  set HF_ENDPOINT=https://hf-mirror.com
  ```

  For PowerShell user:

  ```shell
  $env:HF_ENDPOINT = https://hf-mirror.com
  ```

  If the solution does not work to you / you encountered other issues, please refer to [Frequently Asked Questions](https://github.com/Byaidu/PDFMathTranslate/wiki#-faq--%E5%B8%B8%E8%A7%81%E9%97%AE%E9%A2%98).
</details>


<h2 id="usage">4. Technical Details</h2>

### 4.1 Advanced options

Execute the translation command in the command line to generate the translated document `example-mono.pdf` and the bilingual document `example-dual.pdf` in the current working directory. Use Google as the default translation service. More support translation services can find [HERE](./docs/ADVANCED.md#services).

<img src="./docs/images/cmd.explained.png" width="580px"  alt="cmd"/>

In the following table, we list all advanced options for reference:

| Option                | Function                                                                                                      | Example                                        |
| --------------------- | ------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| files                 | Local files                                                                                                   | `pdf2zh ~/local.pdf`                           |
| links                 | Online files                                                                                                  | `pdf2zh http://arxiv.org/paper.pdf`            |
| `-i`                  | [Enter GUI](#gui)                                                                                             | `pdf2zh -i`                                    |
| `-p`                  | [Partial document translation](./docs/ADVANCED.md#partial) | `pdf2zh example.pdf -p 1`                      |
| `-li`                 | [Source language](./docs/ADVANCED.md#languages)            | `pdf2zh example.pdf -li en`                    |
| `-lo`                 | [Target language](./docs/ADVANCED.md#languages)            | `pdf2zh example.pdf -lo zh`                    |
| `-s`                  | [Translation service](./docs/ADVANCED.md#services)         | `pdf2zh example.pdf -s deepl`                  |
| `-t`                  | [Multi-threads](./docs/ADVANCED.md#threads)                | `pdf2zh example.pdf -t 1`                      |
| `-o`                  | Output dir                                                                                                    | `pdf2zh example.pdf -o output`                 |
| `-f`, `-c`            | [Exceptions](./docs/ADVANCED.md#exceptions)                | `pdf2zh example.pdf -f "(MS.*)"`               |
| `-cp`                 | Compatibility Mode                                                                                            | `pdf2zh example.pdf --compatible`              |
| `--skip-subset-fonts` | [Skip font subset](./docs/ADVANCED.md#font-subset)         | `pdf2zh example.pdf --skip-subset-fonts`       |
| `--ignore-cache`      | [Ignore translate cache](./docs/ADVANCED.md#cache)         | `pdf2zh example.pdf --ignore-cache`            |
| `--share`             | Public link                                                                                                   | `pdf2zh -i --share`                            |
| `--authorized`        | [Authorization](./docs/ADVANCED.md#auth)                   | `pdf2zh -i --authorized users.txt [auth.html]` |
| `--prompt`            | [Custom Prompt](./docs/ADVANCED.md#prompt)                 | `pdf2zh --prompt [prompt.txt]`                 |
| `--onnx`              | [Use Custom DocLayout-YOLO ONNX model]                                                                        | `pdf2zh --onnx [onnx/model/path]`              |
| `--serverport`        | [Use Custom WebUI port]                                                                                       | `pdf2zh --serverport 7860`                     |
| `--dir`               | [batch translate]                                                                                             | `pdf2zh --dir /path/to/translate/`             |
| `--config`            | [configuration file](./docs/ADVANCED.md#cofig)             | `pdf2zh --config /path/to/config/config.json`  |
| `--serverport`        | [custom gradio server port]                                                                                   | `pdf2zh --serverport 7860`                     |
| `--mode`              | Translation mode: `fast` (default, v1) or `precise` (v2, experimental, requires pdf2zh_next submodule)         | `pdf2zh --mode precise example.pdf`            |
| `--babeldoc`          | Use Experimental backend [BabelDOC](https://funstory-ai.github.io/BabelDOC/) to translate                     | `pdf2zh --babeldoc` -s openai example.pdf      |
| `--mcp`               | Enable MCP STDIO mode                                                                                         | `pdf2zh --mcp`                                 |
| `--sse`               | Enable MCP SSE mode                                                                                           | `pdf2zh --mcp --sse`                           |
| `--extract-elements`  | *(fork)* Extract figures and tables as separate image files alongside the translated PDF                      | `pdf2zh example.pdf --extract-elements`        |
| `--word`              | *(fork)* Export translated result as a `.docx` file with embedded images                                     | `pdf2zh example.pdf --word`                    |
| `--markdown`          | *(fork)* Export translated result as `.md` with figures in `images/` subfolder (Obsidian wikilink format)    | `pdf2zh example.pdf --markdown`                |

For detailed explanations, please refer to our document about [Advanced Usage](./docs/ADVANCED.md) for a full list of each option.

<h3 id="downstream">4.2 Downstream Development</h3>
For downstream applications, please refer to our document about [API Details](./docs/APIS.md) for further information about:

- [Python API](./docs/APIS.md#api-python), how to use the program in other Python programs
- [HTTP API](./docs/APIS.md#api-http), how to communicate with a server with the program installed

<h3 id="downstream">4.3 Notable forks</h3>

- [Byaidu/PDFMathTranslate](https://github.com/Byaidu/PDFMathTranslate): The upstream stable release.

- [PDFMathTranslate/PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next): A fork with web-ui and additional features. This fork handles a large number of marginal cases, improves PDF compatibility, and optimizes cross-column and cross-page semantic consistency, dynamic scaling, and dynamic scaling consistency, among many other translation quality improvements. However, this fork is intended solely for development and does not address compatibility issues and is not designed for community-contributions.

- [harveyzhang814/PDFMathTranslate](https://github.com/harveyzhang814/PDFMathTranslate) *(this fork)*: Adds element extraction (`--extract-elements`), column-aware reading order, figure caption pairing, Word document export (`--word`), and Markdown export (`--markdown`) on top of the stable upstream release.

<h2 id="information">5. Project Information</h2>
<h3 id="citation">5.1 Citation</h3>

This work has been accepted by the [*Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing: System Demonstrations*](https://aclanthology.org/2025.emnlp-demos.71/) (EMNLP 2025). 

Citation:

```
@inproceedings{ouyang-etal-2025-pdfmathtranslate,
	    title = "{PDFM}ath{T}ranslate: Scientific Document Translation Preserving Layouts",
	    author = "Ouyang, Rongxin  and
	      Chu, Chang  and
	      Xin, Zhikuang  and
	      Ma, Xiangyao",
	    editor = {Habernal, Ivan  and
	      Schulam, Peter  and
	      Tiedemann, J{\"o}rg},
	    booktitle = "Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing: System Demonstrations",
	    month = nov,
	    year = "2025",
	    address = "Suzhou, China",
	    publisher = "Association for Computational Linguistics",
	    url = "https://aclanthology.org/2025.emnlp-demos.71/",
	    pages = "918--924",
	    ISBN = "979-8-89176-334-0",
	    abstract = "Language barriers in scientific documents hinder the diffusion and development of science and technologies. However, prior efforts in translating such documents largely overlooked the information in layouts. To bridge the gap, we introduce PDFMathTranslate, the world{'}s first open-source software for translating scientific documents while preserving layouts. Leveraging the most recent advances in large language models and precise layout detection, we contribute to the community with key improvements in precision, flexibility, and efficiency. The work is open-sourced at https://github.com/byaidu/pdfmathtranslate with more than 222k downloads."
	}
```
<h3 id="acknowledgement">5.2 Acknowledgement</h3>

- [Immersive Translation](https://immersivetranslate.com) sponsors monthly Pro membership redemption codes for active contributors to this project, see details at: [CONTRIBUTOR_REWARD.md](https://github.com/funstory-ai/BabelDOC/blob/main/docs/CONTRIBUTOR_REWARD.md)

- New backend: [BabelDOC](https://github.com/funstory-ai/BabelDOC)

- Document merging: [PyMuPDF](https://github.com/pymupdf/PyMuPDF)

- Document parsing: [Pdfminer.six](https://github.com/pdfminer/pdfminer.six)

- Document extraction: [MinerU](https://github.com/opendatalab/MinerU)

- Document Preview: [Gradio PDF](https://github.com/freddyaboulton/gradio-pdf)

- Multi-threaded translation: [MathTranslate](https://github.com/SUSYUSTC/MathTranslate)

- Layout parsing: [DocLayout-YOLO](https://github.com/opendatalab/DocLayout-YOLO)

- Document standard: [PDF Explained](https://zxyle.github.io/PDF-Explained/), [PDF Cheat Sheets](https://pdfa.org/resource/pdf-cheat-sheets/)

- Multilingual Font: [Go Noto Universal](https://github.com/satbyy/go-noto-universal)

<h3 id="contrib">5.3 Contributors</h3>

This is a personal fork. For the full contributor list, see the [upstream repository](https://github.com/Byaidu/PDFMathTranslate/graphs/contributors).
