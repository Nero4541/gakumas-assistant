<script setup>
import app from "@/main.js";
const props = defineProps({
  data: Object
})
const runMode = ref([
  {id: "PC", title: "电脑端（DMM）"},
  {id: "Phone", title: "手机端"}
])
</script>

<template>
  <v-list-item>
    <v-select
      label="运行模式"
      hint="脚本的执行模式（需重启生效）"
      :items="runMode"
      item-title="title"
      item-value="id"
      :item-color="app.config.globalProperties.$theme.color"
      v-model="props.data.base.run_mode.value"
      persistent-hint
    />
  </v-list-item>
</template>

<style scoped>

</style>
