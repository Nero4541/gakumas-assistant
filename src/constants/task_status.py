class TaskStatus:
    PENDING = "PENDING"     # 等待执行
    RUNNING = "RUNNING"     # 正在执行
    SUCCESS = "SUCCESS"     # 成功
    RETRY = "RETRY"         # 重试
    FAILED = "FAILED"       # 失败
    CANCELED = "CANCELED"   # 取消
    SUSPENDED = "SUSPENDED" # 挂起