<script setup>
import app from "@/main.js";
import {useAppStore} from "@/stores/app.ts";


const store = useAppStore();
</script>

<template>
  <v-list-item>
    <v-autocomplete
      v-model="store.config.base.disabled_tasks.value"
      :items="Object.entries(store.task_list).map(([k, v]) => ({ id: k, title: v.description }))"
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
