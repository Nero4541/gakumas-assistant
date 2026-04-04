<script setup>
import {useAppStore} from "@/stores/app.ts";
import support_card_whitelist from "@/components/lists/config/task_settings/enhancement_setting/support_card_whitelist.vue";

const props = defineProps({
  task: Object,
  task_name: String,
})

const store = useAppStore()

let task_config = store.get_task_config(props.task_name)

const rarity_max_levels = {
  r: 40,
  sr: 50,
  ssr: 60,
}
</script>

<template>
  <v-form v-auto-save="() => store.save_task_config(task_name)">
    <v-row dense>
      <!-- SSR -->
      <v-col cols="12">
        <v-switch
          label="强化 SSR 卡"
          hint="自动强化SSR品级的支援卡"
          persistent-hint
          density="comfortable"
          v-model="task_config.enhance_ssr.value"
        />
      </v-col>
      <v-col cols="12" v-if="task_config.enhance_ssr.value">
        <v-slider
          label="SSR 最大强化等级"
          v-model="task_config.enhance_ssr_max_level.value"
          :min="1"
          :max="rarity_max_levels.ssr"
          :step="1"
          thumb-label="always"
          density="comfortable"
        />
      </v-col>

      <!-- SR -->
      <v-col cols="12">
        <v-switch
          label="强化 SR 卡"
          hint="自动强化SR品级的支援卡"
          persistent-hint
          density="comfortable"
          v-model="task_config.enhance_sr.value"
        />
      </v-col>
      <v-col cols="12" v-if="task_config.enhance_sr.value">
        <v-slider
          label="SR 最大强化等级"
          v-model="task_config.enhance_sr_max_level.value"
          :min="1"
          :max="rarity_max_levels.sr"
          :step="1"
          thumb-label="always"
          density="comfortable"
        />
      </v-col>

      <!-- R -->
      <v-col cols="12">
        <v-switch
          label="强化 R 卡"
          hint="自动强化R品级的支援卡"
          persistent-hint
          density="comfortable"
          v-model="task_config.enhance_r.value"
        />
      </v-col>
      <v-col cols="12" v-if="task_config.enhance_r.value">
        <v-slider
          label="R 最大强化等级"
          v-model="task_config.enhance_r_max_level.value"
          :min="1"
          :max="rarity_max_levels.r"
          :step="1"
          thumb-label="always"
          density="comfortable"
        />
      </v-col>

      <!-- 白名单模式 -->
      <v-col cols="12">
        <v-divider class="my-2" />
      </v-col>

      <!-- 上限解放 -->
      <v-col cols="12">
        <v-switch
          label="自动执行上限解放"
          hint="有同名卡片且未达到星级上限时，自动进行上限解放（需要持有重复卡片）"
          persistent-hint
          density="comfortable"
          v-model="task_config.auto_limit_break.value"
        />
      </v-col>

      <!-- サポート変換 -->
      <v-col cols="12">
        <v-switch
          label="自动交换溢出的支援卡"
          hint="自动将溢出的支援卡变换为「サポートの証」，可在交换所使用"
          persistent-hint
          density="comfortable"
          v-model="task_config.auto_convert.value"
        />
      </v-col>

      <v-col cols="12">
        <v-divider class="my-2" />
      </v-col>

      <v-col cols="12">
        <v-switch
          label="白名单模式"
          hint="仅强化白名单中选择的卡牌"
          persistent-hint
          density="comfortable"
          v-model="task_config.whitelist_mode.value"
        />
      </v-col>
      <v-col cols="12" v-if="task_config.whitelist_mode.value">
        <support_card_whitelist :data="task_config" />
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
  margin-bottom: 4px;
}
</style>
