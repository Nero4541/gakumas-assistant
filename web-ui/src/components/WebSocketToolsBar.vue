<script setup>
import {computed, ref} from "vue";
import message from "@/scripts/utils/message.js";
import api from "@/scripts/apis.js"
import {useAppStore} from "@/stores/app.js";
import {TaskStatus} from "@/scripts/constants.ts";

const store = useAppStore();
const startingTaskQueue = ref(false)

const canStartTaskQueue = computed(() => {
  if (store.status.task !== TaskStatus.PENDING || startingTaskQueue.value) {
    return false
  }
  if (store.status.platform === "phone") {
    return true
  }
  return store.status.device.available
})

async function startTaskQueue() {
  if (!canStartTaskQueue.value) {
    return
  }
  startingTaskQueue.value = true
  try {
    await api.start_task_queue()
    message.showSuccess("任务正在运行")
  } finally {
    startingTaskQueue.value = false
  }
}
</script>

<template>
  <div class="tools_bar">
    <v-card class="tools_bar__card">
      <v-alert
        v-if="!store.status.device.available"
        class="tools_bar__status_alert"
        title="设备未就绪"
        :text="store.status.platform === 'phone' ? `${store.status.device.message} 点击“开始执行”后会再次尝试连接设备。` : store.status.device.message"
        color="error"
      />
      <v-alert
        v-else-if="store.status.task === TaskStatus.PENDING"
        class="tools_bar__status_alert"
        title="等待操作"
        color="warning"
      />
      <v-alert
        v-else-if="store.status.task === TaskStatus.RUNNING"
        class="tools_bar__status_alert"
        title="脚本执行中......"
        color="success"
      />
      <v-alert
        v-else-if="store.status.task === TaskStatus.SUSPENDED"
        class="tools_bar__status_alert"
        title="脚本挂起中......"
        color="info"
      />
      <div class="tools_bar__actions">
        <v-btn @click="startTaskQueue" color="green" :disabled="!canStartTaskQueue" :loading="startingTaskQueue" v-if="store.status.task === TaskStatus.PENDING">
          开始执行
        </v-btn>
        <v-btn color="red" @click="api.stop_task_queue().then(() => {message.showSuccess('任务正在停止')})" v-else-if="store.status.task === TaskStatus.RUNNING">
          停止任务
        </v-btn>
        <v-btn color="warning" v-if="store.status.task === TaskStatus.RUNNING && store.get_current_task()?.allow_manual_suspend">
          挂起任务
        </v-btn>
        <v-btn color="green" v-if="store.status.task === TaskStatus.SUSPENDED && store.get_current_task()?.allow_manual_resume">
          恢复任务
        </v-btn>
      </div>
    </v-card>
  </div>
</template>

<style scoped>
.tools_bar {
  flex: 0 0 auto;
  min-width: 0;
}

.tools_bar__card {
  margin-bottom: 30px;
  overflow: hidden;
}

.tools_bar__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 20px 15px;
}

.tools_bar__actions :deep(.v-btn) {
  margin-right: 0 !important;
}

.v-alert {
  padding: 25px 15px;
}

.tools_bar__status_alert {
  margin-bottom: 0;
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
}

@media (max-width: 599px) {
  .tools_bar__card {
    margin-bottom: 20px;
  }

  .tools_bar__actions {
    padding: 16px 12px;
  }

  .tools_bar__actions :deep(.v-btn) {
    flex: 1 1 140px;
    min-width: 0;
  }
}
</style>
