<script setup>
import app from "@/main.js";
const props = defineProps({
  data: Object
})

// random|highest_power|lowest_power|balanced_power
const items = [
  {id: "4H", title: "4小时（最低）"},
  {id: "8H", title: "8小时"},
  {id: "12H", title: "12小时（最高）"},
]
</script>

<template>
  <v-select
    label="任务派遣时间"
    hint=""
    :items="items"
    item-title="title"
    item-value="id"
    :item-color="app.config.globalProperties.$theme.color"
    v-model="data.working_hours.value"
    persistent-hint
  />
</template>

<style scoped>

</style>
