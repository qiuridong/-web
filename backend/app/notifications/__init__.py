"""通知系统 — apprise 适配 + 模板渲染 + 事件分发。

详见 `进度/设计/后端架构.md` § 9.4 + § 2.5。

子模块:
- apprise_client.py  apprise 实例池 + 测试发送
- templates.py       默认模板 + Jinja2 渲染 + 自定义 filter(tail/human_duration/local_time)
- dispatcher.py      事件 → 规则匹配 → 渠道发送(异步,不阻塞 run 完成)
"""
