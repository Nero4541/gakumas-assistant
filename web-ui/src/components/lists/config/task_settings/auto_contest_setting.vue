<script setup>
import apis from "@/scripts/apis.js";
import message from "@/scripts/utils/message.js";
import {hash} from "@/scripts/utils/hash.js";
import app from "@/main.js";

const props = defineProps({
  task: Object,
  task_name: String,
})

const configData = ref({})
let configHash
apis.get_task_config(props.task_name).then(response => {
  configData.value = response.data
  configHash = hash(response.data);
})

function save() {
  if (hash(configData.value) === configHash) {
    return;
  }
  apis.save_task_config(props.task_name, configData.value).then(() => {
    message.showSuccess("设置保存成功")
  })
}
</script>

<template>
  <v-form v-auto-save="save">
    <v-row dense v-if="Object.keys(configData).length <= 0">
      <v-col cols="12">
        <v-skeleton-loader type="list-item-two-line"/>
      </v-col>
      <v-col cols="12">
        <v-skeleton-loader type="list-item-two-line"/>
      </v-col>
    </v-row>
    <v-row dense v-else>
      <v-col cols="12">
        <v-switch
          label="挑战前自动重新配置队伍"
          hint="如果队伍中有空位仍会触发自动配置"
          :color="app.config.globalProperties.$theme.color"
          persistent-hint
          v-model="configData.auto_reconfigure_team_before_challenge.value"
        />
      </v-col>
      <v-col cols="12">
        <select_challenge_order :data="configData"/>
      </v-col>
    </v-row>
  </v-form>
</template>

<style scoped>

</style>
