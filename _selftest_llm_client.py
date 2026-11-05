#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_selftest_llm_client.py — 不联网，用本地 mock 验证 llm_client 真实可用。"""
import json
import threading
import http.server
import urllib.request
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm_client  # noqa: E402


class MockHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静默
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        req = json.loads(raw)
        # 校验协议结构
        assert "model" in req and "messages" in req, "missing fields"
        assert req["messages"][-1]["role"] == "user"
        user_text = req["messages"][-1]["content"]
        # 回一个确定性的假回复
        reply = f"[mock] 已收到：{user_text}"
        body = {
            "choices": [{"message": {"role": "assistant", "content": reply}}],
        }
        out = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def run_mock():
    srv = http.server.HTTPServer(("127.0.0.1", 0), MockHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, port


def main():
    srv, port = run_mock()
    base = f"http://127.0.0.1:{port}/v1"
    try:
        # 1) 单轮
        r1 = llm_client.chat("你好", api_key="sk-test", base_url=base)
        assert r1 == "[mock] 已收到：你好", r1
        # 2) 多轮
        msgs = [
            {"role": "user", "content": "我叫支一郎"},
            {"role": "assistant", "content": "你好支一郎"},
            {"role": "user", "content": "我姓什么"},
        ]
        r2 = llm_client.chat_multi(msgs, api_key="sk-test", base_url=base)
        assert r2.startswith("[mock] 已收到：我姓什么"), r2
        # 3) 异常路径：错误 key 仍应走通协议（mock 不校验 key）
        r3 = llm_client.chat("x", api_key="", base_url=base)
        assert "已收到" in r3
        print("PASS: chat / chat_multi 均通过 mock 实测（3/3）")
        print("  r1 =", r1)
        print("  r2 =", r2)
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
