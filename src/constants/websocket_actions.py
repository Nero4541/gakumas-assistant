
class WebsocketActions:
    BaseActionFlag = "action"

    class WebsocketHeartBeat:
        Ping = "ping"
        Pong = "pong"

    class TaskService:
        TaskStatusUpdate = "task:status_update"
        UpdateCurrentTask = "task:update_current_task"
        TaskQueueStart = "task:start"
        TaskQueueStop = "task:stop"
        TaskQueueSuspend = "task:suspend"

    class Message:
        ShowMessage_Info = "show_msg:info"
        ShowMessage_Warning = "show_msg:warning"
        ShowMessage_Error = "show_msg:error"
        ShowMessage_Success = "show_msg:success"

    class Logger:
        BroadcastLog = "broadcast_log"
