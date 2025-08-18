<script setup>
import apis from "@/scripts/apis.js";
import app from "@/main.js";

const props = defineProps({
  data: Object
})
let taskList = ref([])

apis.get_registered_tasks().then((res) => {
  for (const [k, v] of Object.entries(res.data)) {
    taskList.value.push({id:k, title:v.description})
  }
})
console.log(taskList)
</script>

<template>
  <v-list-item>
    <v-autocomplete
      v-model="props.data.base.disabled_tasks.value"
      :items="taskList"
      item-title="title"
      item-value="id"
      :item-color="app.config.globalProperties.$theme.color"
      label="禁用任务列表"
      hint="配置禁用任务列表"
      persistent-hint
      chips
      multiple
    ></v-autocomplete>
  </v-list-item>
</template>

<style scoped>

</style>
