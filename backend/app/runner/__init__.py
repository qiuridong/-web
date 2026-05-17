"""脚本子进程沙箱执行。

详见 `进度/设计/后端架构.md` § 3.4。

子模块:
- sandbox.py        子进程入口,被 `python -m app.runner.sandbox` 调用
- stdio_protocol.py stdin/stdout JSON 协议(__RUN_RESULT__ 标记)
- log_broker.py     实时日志 in-memory broker(供 SSE 订阅)
"""
