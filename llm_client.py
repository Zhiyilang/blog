#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llm_client.py — 零依赖调用大模型（OpenAI 兼容接口）

只依赖 Python 标准库（urllib / json），不装 openai / requests。
适用于 RPA 开发者所在的受限企业环境：pip 被封、不能装包，也能跑。

用法：
    from llm_client import chat
    reply = chat("你好", api_key="sk-xxx")
    print(reply)
"""
from __future__ import annotations
import json
import urllib.request
import urllib.error

DEFAULT_BASE_URL = "https://api.openai.com/v1"


def chat(
    prompt: str,
    *,
    api_key: str,
    model: str = "gpt-4o-mini",
    base_url: str = DEFAULT_BASE_URL,
    system: str = "你是一个简洁有帮助的助手。",
    temperature: float = 0.7,
    timeout: float = 30.0,
) -> str:
    """发送一条用户消息，返回模型回复文本。

    Args:
        prompt: 用户输入。
        api_key: OpenAI 兼容接口的密钥。
        model: 模型名。
        base_url: 接口根地址（兼容本地/第三方大模型网关）。
        system: 系统提示。
        temperature: 采样温度。
        timeout: 单次请求超时（秒）。
    Returns:
        模型生成的文本。
    Raises:
        RuntimeError: 接口返回非 200 或 body 结构异常。
    """
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
    try:
        obj = json.loads(body)
        return obj["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        raise RuntimeError(f"无法解析响应: {body[:200]}") from e


def chat_multi(
    messages: list[dict],
    *,
    api_key: str,
    model: str = "gpt-4o-mini",
    base_url: str = DEFAULT_BASE_URL,
    temperature: float = 0.7,
    timeout: float = 30.0,
) -> str:
    """多轮对话版：直接传入 messages 列表。

    messages 形如 [{"role":"user","content":"..."}, ...]
    """
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": temperature}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + api_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')}") from e
    obj = json.loads(body)
    return obj["choices"][0]["message"]["content"]


if __name__ == "__main__":
    # 自测：需要真实 api_key 时才联网；否则用 _selftest 跑 mock。
    print("llm_client module loaded. import chat / chat_multi.")
