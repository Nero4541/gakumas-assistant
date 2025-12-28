<script setup>
import apis from "@/scripts/apis.js";
import message from "@/scripts/utils/message.js";
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
          label="挑战前自动重新配置队伍"
          hint="如果队伍中有空位仍会触发自动配置"
          :color="app.config.globalProperties.$theme.color"
          persistent-hint
          v-model="task_config.auto_reconfigure_team_before_challenge.value"
        />
      </v-col>
      <v-col cols="12">
        <select_challenge_order :data="task_config"/>
      </v-col>
    </v-row>
  </v-form>
</template>

<style scoped>

</style>
