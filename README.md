# 支一郎的技术博客

> RPA 开发转 AI Agent 工程的实战笔记。全部零依赖 Python、可复现、附实测数据。

[![awesome](https://img.shields.io/badge/awesome-RPA%E2%86%92AI%20Agent-blue)](https://github.com/Zhiyilang/awesome-rpa-to-ai-agent)
[![tools](https://img.shields.io/badge/%E9%9B%B6%E4%BE%9D%E8%B5%96%E5%B7%A5%E5%85%B7-6%20%E4%B8%AA-green)](https://zhiyilang.github.io/)

## 文章

- [把 RPA 流程一键编译成 MCP Server](01-rpa2mcp.md) — 不重写逻辑，把影刀/UiBot 流程的每一步暴露成 MCP 工具（7 步→9 个工具，4 项测试全绿）
- [零依赖 Python 实战：UiBot 里的 Excel 自动化三件套](02-uibot-excel.md) — 不装 openpyxl/pandas，纯标准库读写 xlsx（合并/透视/核对，17 项测试全绿）
- [没有浏览器怎么测 RPA 流程？Mock 干跑与「宣称=实测」闸门](03-rpa2test.md) — dryrun + verify + 表达式沙箱（21 项测试全绿）
- [零依赖调用大模型：RPA 开发者在受限环境也能跑 LLM](04-llm-client.md) — 不装 openai 包，纯 urllib 调 OpenAI 兼容接口（mock 实测 3/3）

## 配套代码

- `llm_client.py` — 本文第 4 篇的零依赖大模型客户端（urllib 实现）
- `_selftest_llm_client.py` — 本地 mock 自测，不联网验证协议正确性

## 关于作者

支一郎 — RPA 开发 → AI Agent 工程。作品集与接单入口：[zhiyilang.github.io](https://zhiyilang.github.io/)

RPA 转 Agent 精选路线图（带可复制代码）：[awesome-rpa-to-ai-agent](https://github.com/Zhiyilang/awesome-rpa-to-ai-agent)

*本博客所有文章均为真实项目实测，命令可复现。*
