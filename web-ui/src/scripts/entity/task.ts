export interface TaskItem {
  description: string
  enable: boolean
  last_run_time: number
  start_time: number
  status: string
  allow_manual_suspend: boolean
  allow_manual_resume: boolean
}
