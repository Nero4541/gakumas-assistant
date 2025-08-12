<script setup>
import apis from "@/scripts/apis.js";

const props = defineProps({
  data: Object
})
</script>

<template>
  <v-navigation-drawer>
    <v-list nav>
      <v-list-item title="任务列表"/>
      <v-divider/>
      <!--      <v-list-item v-for="(data, task_name) in task_list" :key="task_name" :title="`${data.description} (${task_name})`" />-->
      <v-expansion-panels variant="accordion">
        <v-expansion-panel
          v-for="(data, task_name) in props.data" :key="task_name"
        >
          <v-expansion-panel-title disable-icon-rotate>
            <strong>{{ data.description }}</strong>
            <template v-slot:actions>
              <v-icon v-if="data.status === 'PENDING'" color="rgb(243,142,61)" icon="schedule" title="等待中"/>
              <v-icon v-else-if="data.status === 'RUNNING'" color="green" icon="cached" class="running" title="运行中"/>
              <v-icon v-else-if="data.status === 'SUCCESS'" color="green" icon="task_alt" title="已完成"/>
              <v-icon v-else-if="data.status === 'FAILED'" color="error" icon="error" title="执行时发生错误"/>
              <v-icon v-else-if="data.status === 'CANCELED'" color="grey" icon="cancel" title="已取消"/>
              <v-icon v-else icon="indeterminate_question_box" title="未知状态"/>
            </template>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <p>任务名：{{ task_name }}</p>
            <p>状态：{{ data.status }}</p>
            <p>启用：{{ data.enable ? "启用" : "禁用" }}</p>
            <p>上次运行时间：{{ data.last_run_time > 0 ? data.last_run_time : "未运行" }}</p>
            <div class="task_tools_bar">
              <v-btn :disabled="data.status === 'RUNNING'" @click="apis.run_task(task_name)">执行</v-btn>
              <v-btn v-if="data.enable" color="red" @click="apis.disable_task(task_name)">禁用</v-btn>
              <v-btn v-else color="green" @click="apis.enable_task(task_name)">启用</v-btn>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </v-list>
  </v-navigation-drawer>
</template>

<style scoped>
.task_tools_bar {
  margin-top: 10px;
  display: flex;
  .v-btn:not(:last-child) {
    margin-right: 5px;
  }
}
</style>
