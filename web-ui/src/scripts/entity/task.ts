export interface TaskItem {
  description: string
  enable: boolean
  last_run_time: number
  start_time: number
  status: string
  manual_only: boolean
  allow_manual_suspend: boolean
  allow_manual_resume: boolean
}
