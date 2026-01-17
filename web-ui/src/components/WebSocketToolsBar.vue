<script setup>
import message from "@/scripts/utils/message.js";
import api from "@/scripts/apis.js"
import {useAppStore} from "@/stores/app.js";
import {TaskStatus} from "@/scripts/constants.ts";

const store = useAppStore();

</script>

<template>
  <v-alert
    v-if="store.status.task === TaskStatus.PENDING"
    title="等待操作"
    color="warning"
  />
  <v-alert
    v-else-if="store.status.task === TaskStatus.RUNNING"
    title="脚本执行中......"
    color="success"
  />
  <v-alert
    v-else-if="store.status.task === TaskStatus.SUSPENDED"
    title="脚本挂起中......"
    color="info"
  />
  <v-card>
    <v-btn @click="api.start_task_queue().then(message.showSuccess('任务正在运行'))" color="green" v-if="store.status.task === TaskStatus.PENDING">
      开始执行
    </v-btn>
    <v-btn color="red" @click="api.stop_task_queue().then(() => {message.showSuccess('任务正在停止')})" v-else-if="store.status.task === TaskStatus.RUNNING">
      停止任务
    </v-btn>
    <v-btn color="warning" v-if="store.status.task === TaskStatus.RUNNING && store.get_current_task().allow_manual_suspend">
      挂起任务
    </v-btn>
    <v-btn color="green" v-if="store.status.task === TaskStatus.SUSPENDED && store.get_current_task().allow_manual_resume">
      恢复任务
    </v-btn>
  </v-card>
</template>

<style scoped>
.v-card {
  padding: 20px 15px;
  margin-bottom: 30px;
  .v-btn:not(:last-child) {
    margin-right: 10px;
  }
}
.v-alert {
  padding: 25px 15px;
}
</style>
