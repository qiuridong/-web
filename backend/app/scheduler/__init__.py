"""调度引擎 — APScheduler 3.x AsyncIOScheduler 同进程模式。

详见 `进度/设计/后端架构.md` § 4。

子模块:
- engine.py        APScheduler 封装 + 启停 + 任务注册接口
- executor.py      单次执行的全流程编排(§ 4.4)
- concurrency.py   并发槽位 Semaphore + 排队
- retry.py         失败重试策略(指数退避)
"""
