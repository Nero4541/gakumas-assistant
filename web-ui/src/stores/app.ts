// Utilities
import { defineStore } from 'pinia'
import apis from '@/scripts/apis'
import { WS_ACTION } from '@/scripts/constants'
import { wsService } from "@/scripts/utils/websocket";
import message from "@/scripts/utils/message";
import {AppStatus} from "@/scripts/entity/status";
import {TaskItem} from "@/scripts/entity/task";
import {ConfigItem} from "@/scripts/entity/config";

/** Store State */
export interface AppState {
  status: AppStatus
  task_list: Record<string, TaskItem>
  config: Record<string, Record<string, ConfigItem>>
}

export const useAppStore = defineStore('app', {
  state: (): AppState => ({
    status: {
      platform: '',
      yolo: false,
      task: false,
      game: {
        current_location: '',
        player: {
          level: 0,
          gem: 0,
          stamina: 0
        }
      }
    },
    task_list: {},
    config: {}
  }),
  actions: {
    async init() {
      await this.refresh_all_data()
      wsService.on(WS_ACTION.TaskStatusUpdate, (data) => {
        const task: TaskItem = this.task_list?.[data.id]
        if (!task) {
          console.warn(`Update undefined task status: ${data.id}`)
          return
        }
        console.log(`Update task '${data.id}' status: ${task.status} -> ${data.target_status}`)
        task.status = data.target_status
      })
      wsService.on(WS_ACTION.TaskQueueStart, () => {
        this.status.task = true
      })
      wsService.on(WS_ACTION.TaskQueueStop, () => {
        this.status.task = false
      })
      wsService.on(WS_ACTION.BroadcastLog, (data) => {
        console.log(data)
      })
      wsService.onEvent("reconnect", async () => {
        await this.refresh_all_data()
      })
    },
    async refresh_all_data() {
      await this.refresh_task_list()
      await this.refresh_app_status()
      await this.load_config()
      console.log(this.$state)
    },
    async refresh_task_list() {
      const response = await apis.get_registered_tasks()
      this.task_list = response.data
    },
    async refresh_app_status() {
      const response = await apis.get_status()
      this.status = response.data
    },
    async load_config() {
      const response = await apis.get_config()
      this.config = response.data
    },
    async save_config() {
      await apis.save_config(this.config).then((response) => {
        this.config = response.data
        message.showSuccess("设置保存成功")
      })
    },
    get_task_config(task_name: string) {
      console.log(`task__${task_name}`,this.config?.[`task__${task_name}`])
      return toRef(this.config, `task__${task_name}`)
    },
    async save_task_config(task_name: string) {
      await apis.save_task_config(task_name, this.config?.[`task__${task_name}`]).then((response) => {
        const target_config = `task__${task_name}`
        this.config[target_config] = response.data
        message.showSuccess("设置保存成功")
      })
    },
    async reset_config() {
      await apis.reset_config().then(response => {
        this.config = response.data
        message.showSuccess("设置重置完成，部分设置可能需要重启生效")
      })
    }
  }
})
