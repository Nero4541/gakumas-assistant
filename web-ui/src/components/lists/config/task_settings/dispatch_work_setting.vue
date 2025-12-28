<script setup>
import app from "@/main.js";
import {useAppStore} from "@/stores/app.ts";

const props = defineProps({
  task: Object,
  task_name: String,
})

const store = useAppStore()

let task_config = store.get_task_config(props.task_name)
</script>

<template>
  <v-form v-auto-save="() => store.save_task_config(task_name)">
    <v-row dense>
      <v-col cols="12">
        <v-switch
          label="重新配置任务派遣时间"
          hint=""
          :color="app.config.globalProperties.$theme.color"
          persistent-hint
          v-model="task_config.reconfigure_work_hours.value"
        />
      </v-col>
      <v-col cols="12">
        <select_working_hours v-if="task_config.reconfigure_work_hours.value" :data="task_config"/>
      </v-col>
    </v-row>
  </v-form>
</template>

<style scoped>

</style>
