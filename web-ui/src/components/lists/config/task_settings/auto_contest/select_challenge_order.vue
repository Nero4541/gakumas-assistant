<script setup>
import app from "@/main.js";
const props = defineProps({
  data: Object
})

// random|highest_power|lowest_power|balanced_power
const items = [
  {id: "random", title: "随机选择"},
  {id: "highest_power", title: "最高"},
  {id: "lowest_power", title: "最低"},
  {id: "balanced_power", title: "中间"},
]
</script>

<template>
  <v-select
    label="挑战顺序"
    hint="脚本会按照设定的挑战顺序寻找符合的挑战对象（默认随机）"
    :items="items"
    item-title="title"
    item-value="id"
    :item-color="app.config.globalProperties.$theme.color"
    v-model="data.challenge_order.value"
    persistent-hint
  />
</template>

<style scoped>

</style>
