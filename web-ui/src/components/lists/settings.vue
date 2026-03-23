<script setup>
import apis from "@/scripts/apis.js";
import ConfigAutoField from "@/components/lists/config/config_auto_field.vue";
import dialogs from "@/scripts/utils/dialogs.js";
import message from "@/scripts/utils/message.js";
import {useAppStore} from "@/stores/app.ts";

const appStore = useAppStore();
const autoSections = ["base", "dmm_player"]

const settingEntries = computed(() => {
  const entries = []
  for (const sectionName of autoSections) {
    const section = appStore.config?.[sectionName]
    if (!section) {
      continue
    }
    for (const [fieldName, item] of Object.entries(section)) {
      if (!item?.ui?.auto_generate) {
        continue
      }
      if (!isVisible(item.ui?.visible_if)) {
        continue
      }
      entries.push({
        key: `${sectionName}.${fieldName}`,
        sectionName,
        fieldName,
        item,
        order: item.ui?.order ?? 0,
      })
    }
  }
  return entries.sort((left, right) => left.order - right.order)
})

const showDmmRefresh = computed(() => appStore.config?.base?.run_mode?.value === "PC")

function getConfigValue(path) {
  const [sectionName, fieldName] = path.split(".")
  return appStore.config?.[sectionName]?.[fieldName]?.value
}

function isVisible(visibleIf) {
  if (!visibleIf) {
    return true
  }
  return Object.entries(visibleIf).every(([path, expected]) => {
    const currentValue = getConfigValue(path)
    if (Array.isArray(expected)) {
      return expected.includes(currentValue)
    }
    return currentValue === expected
  })
}

function shouldShowDivider(entryKey) {
  return entryKey === "base.enabled_auto_startup"
}

async function refreshDmmPlayerToken() {
  await apis.refresh_ddm_player_token()
  await appStore.load_config()
  await message.showSuccess("启动参数刷新成功")
}

function reset() {
  dialogs.confirm("是否要重置所有设置项", "请谨慎操作，该操作回导致所有设置项恢复默认（包括任务设置）").then(() => {
    appStore.reset_config();
  }).catch(() => {
    console.log("用户取消")
  })
}
</script>

<template>
  <v-navigation-drawer permanent width="400">
    <v-card title="脚本设置" class="pa-3"></v-card>
    <v-divider/>
    <v-list nav>
      <v-list-item subtitle="基础设置"/>
      <template v-for="entry in settingEntries" :key="entry.key">
        <v-divider v-if="shouldShowDivider(entry.key)" />
        <ConfigAutoField :config="appStore.config" :item="entry.item" />
      </template>
      <v-list-item v-if="showDmmRefresh">
        <v-btn
          block
          append-icon="md:refresh"
          @click="refreshDmmPlayerToken"
        >
          刷新启动参数
        </v-btn>
      </v-list-item>
    </v-list>
    <template v-slot:append>
      <div class="pa-2 mb-2 mt-2">
        <v-btn
          class="mr-2"
          @click="appStore.save_config()"
          color="green"
          append-icon="md:save"
        >
          保存设置
        </v-btn>
        <v-btn
          @click="reset()"
          color="warning"
          append-icon="md:restart_alt"
        >
          恢复默认
        </v-btn>
      </div>
    </template>
  </v-navigation-drawer>
</template>
