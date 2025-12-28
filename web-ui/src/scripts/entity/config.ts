export interface ConfigItem<T = any> {
  value: T
  default_value: T
  verify: string
  use_verify: boolean
  last_modified_time: string
}
