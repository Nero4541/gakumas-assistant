<script setup lang="ts">
import app from "@/main.js";
const props = defineProps({
  data: Object
})

const items = [
  {id: "Network", title: "网络连接"},
  {id: "USB", title: "USB连接"}
]
</script>

<template>
  <v-list-item>
    <v-select
      label="ADB连接模式"
      hint="安卓调试桥的连接模式，手机建议使用USB，模拟器可使用网络连接（修改后需重启生效）"
      :items="items"
      item-title="title"
      item-value="id"
      :item-color="app.config.globalProperties.$theme.color"
      v-model="props.data.base.adb_connect_mode.value"
      persistent-hint
    ></v-select>
  </v-list-item>
</template>

<style scoped>

</style>
