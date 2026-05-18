# 部署为公共服务

## 基础部署（Docker）

```bash
docker pull byaidu/pdf2zh
docker run -d -p 7860:7860 byaidu/pdf2zh
```

浏览器访问 `http://your-server:7860/`

---

## 限制可用翻译服务

在配置文件中设置 `ENABLED_SERVICES`，只向用户暴露指定服务：

```json
{
    "ENABLED_SERVICES": ["OpenAI", "Grok"],
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
            "name": "grok",
            "envs": {
                "GROK_BASE_URL": "https://api.x.ai/v1",
                "GROK_API_KEY": "your-key",
                "GROK_MODEL": "grok-2-1212"
            }
        }
    ]
}
```

---

## 隐藏 API Key

设置 `HIDDEN_GRADIO_DETAILS: true` 防止 Web UI 泄露服务器端 API Key：

```json
{
    "HIDDEN_GRADIO_DETAILS": true
}
```

---

## 配置 GUI 授权

限制只有指定用户才能访问 Web UI：

```bash
pdf2zh -i --authorized users.txt auth.html
```

`users.txt`——每行一个账户，逗号分隔用户名和密码：

```
admin,your-password
user1,password1
```

`auth.html`（可选）——自定义登录页面 HTML。

---

## 云平台一键部署

[![Deploy on Heroku](https://www.herokucdn.com/deploy/button.svg)](https://www.heroku.com/deploy?template=https://github.com/Byaidu/PDFMathTranslate)
[![Deploy on Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)
[![Deploy on Zeabur](https://zeabur.com/button.svg)](https://zeabur.com/templates/5FQIGX?referralCode=reycn)
