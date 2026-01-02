export const WS_ACTION_HEAD = 'action' as const

export const WS_ACTION = {
  TaskStatusUpdate: 'task:status_update',
  TaskQueueStart: 'task:start',
  TaskQueueStop: 'task:stop',

  ShowMessage_Info: 'show_msg:info',
  ShowMessage_Warning: 'show_msg:warning',
  ShowMessage_Error: 'show_msg:error',
  ShowMessage_Success: 'show_msg:success',

  BroadcastLog: 'broadcast_log',
  Ping: 'ping',
  Pong: 'pong',
} as const

export const TaskStatus = {
  PENDING: "PENDING",
  RUNNING: "RUNNING",
  SUCCESS: "SUCCESS",
  RETRY: "RETRY",
  FAILED: "FAILED",
  CANCELED: "CANCELED",
  SUSPENDED: "SUSPENDED"
} as const
