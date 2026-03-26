export interface ResourceRepositoryStatus {
  name: string
  path: string
  exists: boolean
  dirty: boolean
  has_update: boolean
  local_commit: string
  remote_commit: string
  local_commit_short: string
  remote_commit_short: string
  error: string
}

export interface ResourceUpdateStatus {
  enabled: boolean
  check_on_startup: boolean
  check_period: string
  interval_minutes: number
  checking: boolean
  updating: boolean
  has_update: boolean
  last_checked_at: string | null
  next_check_at: string | null
  last_error: string
  update_signature: string
  repositories: ResourceRepositoryStatus[]
}
