<script setup>
import apis from "@/scripts/apis.js";
import message from "@/scripts/utils/message.js";

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
  <v-row dense v-if="Object.keys(configData).length <= 0">
    <v-col cols="12">
      <v-skeleton-loader type="list-item-two-line" />
    </v-col>
    <v-col cols="12">
      <v-skeleton-loader type="list-item-two-line" />
    </v-col>
    <v-col cols="12">
      <v-skeleton-loader type="button" />
    </v-col>
  </v-row>
  <v-row dense v-else>
    <v-col cols="12">
      <v-switch
        label="购买每周礼包"
        hint="每日检查礼包页面是否有免费可购买项"
        persistent-hint
        clearable
        density="comfortable"
        v-model="configData.weekly_gift.value"
      />
    </v-col>
    <v-col cols="12">
      <v-autocomplete
        label="每日购买物品列表"
        hint=""
        persistent-hint
        clearable
        density="comfortable"
        v-model="configData.daily_buy_list.value"
      />
    </v-col>
    <v-col cols="12" class="d-flex mt-3" style="gap: 8px">
      <v-btn block text="保存" @click="save"/>
    </v-col>
  </v-row>
</template>

<style scoped>
.v-row {
  padding-top: 15px;
}
.v-text-field,
.v-select,
.v-autocomplete,
.v-switch,
.v-slider,
.v-textarea {
  margin-bottom: 12px;
}
</style>
