# 零依赖调用大模型：RPA 开发者在受限环境也能跑 LLM

> 关键词：RPA 调用大模型 / 不装 openai 包 / 纯 Python 标准库 / 企业内网受限环境 / OpenAI 兼容接口

## 痛点

影刀、UiBot 这类 RPA 工具跑在客户机器或企业内网里，常常：

- `pip install openai` 被封，连不上 PyPI；
- 环境是 Python 3.8，装新包要一堆依赖；
- 安全策略只允许标准库。

但业务又想让流程「接大模型」：自动写周报、解析工单、把截图丢给视觉模型。

答案很简单：**大模型接口本质就是一个 HTTP POST + JSON**。Python 标准库 `urllib` 就够了，零依赖、零安装。

## 核心代码（已实测）

下面这个 `llm_client.py` 只用了 `urllib` 和 `json`，兼容 OpenAI 官方接口，也能指向任意第三方 / 本地网关。

```python
import json
import urllib.request
import urllib.error

def chat(prompt, *, api_key, model="gpt-4o-mini",
         base_url="https://api.openai.com/v1",
         system="你是一个简洁有帮助的助手。",
         temperature=0.7, timeout=30.0):
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + api_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')}") from e
    return json.loads(body)["choices"][0]["message"]["content"]
```

调用就一行：

```python
reply = chat("把这段工单摘要成一句话", api_key="sk-xxx")
print(reply)
```

## 实测记录

我写了 `_selftest_llm_client.py`，用本地 `http.server` 起一个 mock 接口，不联网验证协议正确性：

```
PASS: chat / chat_multi 均通过 mock 实测（3/3）
  r1 = [mock] 已收到：你好
  r2 = [mock] 已收到：我姓什么
```

覆盖了：单轮消息、多轮 `messages` 列表、异常错误码透传。代码和测试都在本仓库根目录（`llm_client.py` / `_selftest_llm_client.py`），可直接复制使用。

## 接 RPA 的三个真实场景

1. **工单 / 邮件自动摘要**：把抓取到的文本塞进 `prompt`，返回摘要写回 Excel 或发邮件。
2. **非结构化 PDF / 网页抽取**：先自己用标准库解析，再把脏文本交给模型结构化（`返回 JSON：{客户名, 金额, 截止日}`）。
3. **视觉模型**：把截图 base64 进 `messages` 的 `image_url` 字段（多模态接口同样只是换 JSON 结构），让模型读图。

## 注意事项

- **密钥别硬编码**：从环境变量或加密配置读 `api_key`，别写死在流程里。
- **超时与重试**：企业网络不稳，建议加 `timeout` 和最多 3 次指数退避。
- **国产模型平替**：把 `base_url` 换成兼容网关（如某国产大模型的 `/v1` 地址），其余代码不变。

## 延伸

- 把 RPA 流程编译成 MCP Server：[01-rpa2mcp.md](01-rpa2mcp.md)
- RPA 转 Agent 精选路线图：[awesome-rpa-to-ai-agent](https://github.com/Zhiyilang/awesome-rpa-to-ai-agent)
- 零依赖 Python 工具合集：[zhiyilang.github.io](https://zhiyilang.github.io/)

---

*本文代码均为真实可运行片段，`_selftest` 在本地 mock 下 3/3 通过。*
