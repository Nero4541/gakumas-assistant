<script setup>
import message from "@/scripts/utils/message.js";
import api from "@/scripts/apis.js"
import {useAppStore} from "@/stores/app.js";
import {TaskStatus} from "@/scripts/constants.ts";

const store = useAppStore();

</script>

<template>
  <v-card>
    <v-btn @click="api.start_task_queue().then(message.showSuccess('任务正在运行'))" color="green" v-if="store.status.task === TaskStatus.PENDING">
      开始执行
    </v-btn>
    <v-btn color="red" @click="api.stop_task_queue().then(() => {message.showSuccess('任务正在停止')})" v-else>
      停止任务
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
</style>
