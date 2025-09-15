<script setup>
import apis from "@/scripts/apis.js";
import message from "@/scripts/utils/message.js";
import app from "@/main.js";

const props = defineProps({
  task: Object,
  task_name: String,
})

const configData = ref({})
apis.get_task_config(props.task_name).then(response => {
  configData.value = response.data
})

function save() {
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
          label="重新配置任务派遣时间"
          hint=""
          :color="app.config.globalProperties.$theme.color"
          persistent-hint
          v-model="configData.reconfigure_work_hours.value"
        />
      </v-col>
      <v-col cols="12">
        <select_working_hours v-if="configData.reconfigure_work_hours.value" :data="configData"/>
      </v-col>
    </v-row>
  </v-form>
</template>

<style scoped>

</style>
