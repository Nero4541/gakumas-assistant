<script setup>
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
          label="购买每周礼包"
          hint="每日检查礼包页面是否有免费可购买项"
          persistent-hint
          clearable
          density="comfortable"
          v-model="task_config.weekly_gift.value"
        />
      </v-col>
      <v-col cols="12">
        <v-switch
          label="自动刷新交换所"
          hint="每日自动刷新交换所"
          persistent-hint
          clearable
          density="comfortable"
          v-model="task_config.refresh_shop.value"
        />
      </v-col>
      <v-col cols="12" v-if="task_config.refresh_shop.value">
        <v-switch
          label="使用钻石刷新交换所"
          clearable
          density="comfortable"
          v-model="task_config.use_gem_refresh.value"
        />
      </v-col>
      <v-col cols="12">
        <select_item :data="task_config"/>
      </v-col>
    </v-row>
  </v-form>
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
