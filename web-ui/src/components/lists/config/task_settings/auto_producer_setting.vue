<script setup>
import app from "@/main.js";
import {useAppStore} from "@/stores/app.ts";
import {computed} from "vue";

const props = defineProps({
  task: Object,
  task_name: String,
})

const store = useAppStore()
let task_config = store.get_task_config(props.task_name)

const themeColor = app.config.globalProperties.$theme.color

const scenarioOptions = [
  {title: "初", value: "hajime"},
  {title: "NIA", value: "nia"},
]

const hajimeDifficultyOptions = [
  {title: "Regular", value: "regular"},
  {title: "Pro", value: "pro"},
  {title: "Master", value: "master"},
  // {title: "Legend", value: "legend"},
]

const niaDifficultyOptions = [
  {title: "Pro", value: "pro"},
  {title: "Master", value: "master"},
]

const formationModeOptions = [
  {title: "自动编成", value: "auto"},
  {title: "预设编号", value: "preset"},
]

const configReady = computed(() => Boolean(task_config.value?.scenario))

// 兼容旧配置：target_idol_card_name → target_idol_card_id
const idolCardField = computed(() =>
  task_config.value?.target_idol_card_id ?? task_config.value?.target_idol_card_name ?? null
)

const showHajimeDifficulty = computed(() => task_config.value?.scenario?.value === "hajime")
const showNiaDifficulty = computed(() => task_config.value?.scenario?.value === "nia")
const showSupportPreset = computed(() => task_config.value?.support_card_mode?.value === "preset")
const showMemoryPreset = computed(() => task_config.value?.memory_mode?.value === "preset")
</script>

<template>
  <v-form v-if="configReady" v-auto-save="() => store.save_task_config(task_name)">
    <v-row dense>
      <v-col cols="12">
        <v-select
          label="剧本"
          hint="选择培育剧本"
          :color="themeColor"
          :item-color="themeColor"
          :items="scenarioOptions"
          item-title="title"
          item-value="value"
          density="comfortable"
          persistent-hint
          v-model="task_config.scenario.value"
        />
      </v-col>
      <v-col cols="12" v-if="showHajimeDifficulty">
        <v-select
          label="难度"
          hint="选择培育难度"
          :color="themeColor"
          :item-color="themeColor"
          :items="hajimeDifficultyOptions"
          item-title="title"
          item-value="value"
          density="comfortable"
          persistent-hint
          v-model="task_config.difficulty.value"
        />
      </v-col>
      <v-col cols="12" v-if="showNiaDifficulty">
        <v-select
          label="NIA 难度"
          hint="选择 NIA 剧本难度"
          :color="themeColor"
          :item-color="themeColor"
          :items="niaDifficultyOptions"
          item-title="title"
          item-value="value"
          density="comfortable"
          persistent-hint
          v-model="task_config.nia_difficulty.value"
        />
      </v-col>
      <v-col cols="12" v-if="idolCardField">
        <idol_card_browser :data="task_config"/>
      </v-col>
      <v-col cols="12">
        <v-select
          label="支援卡编成"
          hint="自动编成（おまかせ）或使用预设编号"
          :color="themeColor"
          :item-color="themeColor"
          :items="formationModeOptions"
          item-title="title"
          item-value="value"
          density="comfortable"
          persistent-hint
          v-model="task_config.support_card_mode.value"
        />
      </v-col>
      <v-col cols="12" v-if="showSupportPreset">
        <v-text-field
          label="支援卡预设编号"
          hint="使用第几组预设编成"
          :color="themeColor"
          type="number"
          density="comfortable"
          persistent-hint
          v-model.number="task_config.support_card_preset_index.value"
        />
      </v-col>
      <v-col cols="12">
        <v-select
          label="记忆编成"
          hint="自动编成（おまかせ）或使用预设编号"
          :color="themeColor"
          :item-color="themeColor"
          :items="formationModeOptions"
          item-title="title"
          item-value="value"
          density="comfortable"
          persistent-hint
          v-model="task_config.memory_mode.value"
        />
      </v-col>
      <v-col cols="12" v-if="showMemoryPreset">
        <v-text-field
          label="记忆预设编号"
          hint="使用第几组预设编成"
          :color="themeColor"
          type="number"
          density="comfortable"
          persistent-hint
          v-model.number="task_config.memory_preset_index.value"
        />
      </v-col>
      <v-col cols="12">
        <v-switch
          label="使用租赁记忆（レンタルを使用）"
          hint="自动编排记忆时勾选租赁复选框"
          :color="themeColor"
          density="comfortable"
          persistent-hint
          v-model="task_config.use_rental.value"
        />
      </v-col>
      <v-col cols="12">
        <v-switch
          label="使用加成道具"
          hint="開始確認页面是否使用加成道具（編成詳細按钮上方）"
          :color="themeColor"
          density="comfortable"
          persistent-hint
          v-model="task_config.use_boost_items.value"
        />
      </v-col>
      <v-col cols="12">
        <v-switch
          label="恢复中断的培育"
          hint="检测到上次中断的培育时自动恢复（点击「再開する」），而非放弃重新开始（要求回到主界面）"
          :color="themeColor"
          density="comfortable"
          persistent-hint
          v-model="task_config.resume_interrupted.value"
        />
      </v-col>
    </v-row>
  </v-form>
  <div v-else class="pa-4 text-body-2 text-medium-emphasis">
    配置加载中…如长时间未显示请重启后端服务以应用配置更新。
  </div>
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
