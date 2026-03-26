<script setup>
import { computed } from "vue";
import apis from "@/scripts/apis.js";
import ConfigAutoField from "@/components/lists/config/config_auto_field.vue";
import dialogs from "@/scripts/utils/dialogs.js";
import message from "@/scripts/utils/message.js";
import {useAppStore} from "@/stores/app.ts";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: true,
  },
  temporary: {
    type: Boolean,
    default: false,
  },
  disableTransition: {
    type: Boolean,
    default: false,
  },
  width: {
    type: [Number, String],
    default: 400,
  },
})
const emit = defineEmits(["update:modelValue"])
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
const showResourceUpdateTools = computed(() => Boolean(appStore.config?.base))
const resourceUpdateBusy = computed(() => Boolean(appStore.resource_update_status?.checking || appStore.resource_update_status?.updating))
const resourceUpdateStatusText = computed(() => appStore.build_resource_update_status_text(appStore.resource_update_status))
const resourceUpdateHasUpdate = computed(() => Boolean(appStore.resource_update_status?.has_update))
const resourceUpdateLastError = computed(() => appStore.resource_update_status?.last_error || "")
const resourceUpdateStateLabel = computed(() => {
  const status = appStore.resource_update_status
  if (status?.updating) {
    return "更新中"
  }
  if (status?.checking) {
    return "检查中"
  }
  if (status?.has_update) {
    return "发现更新"
  }
  if (status?.last_error) {
    return "检查异常"
  }
  if (status?.last_checked_at) {
    return "已检查"
  }
  return "待检查"
})
const resourceUpdateStateColor = computed(() => {
  const status = appStore.resource_update_status
  if (status?.updating || status?.checking) {
    return "primary"
  }
  if (status?.has_update) {
    return "warning"
  }
  if (status?.last_error) {
    return "error"
  }
  return "success"
})
const resourceUpdateHeadline = computed(() => {
  const status = appStore.resource_update_status
  if (status?.updating) {
    return "正在同步资源仓库并重新加载游戏数据库"
  }
  if (status?.checking) {
    return "正在检查 GakumasTranslationData 和 gakumasu-diff 的上游更新"
  }
  if (status?.has_update) {
    return "发现资源仓库新版本，可以立即更新"
  }
  if (status?.last_error) {
    return "最近一次检查存在异常"
  }
  if (status?.last_checked_at) {
    return "当前资源仓库状态已同步"
  }
  return "可手动检查，也可等待启动或定时检查"
})
const resourceUpdateNoticeClass = computed(() => {
  switch (appStore.resource_update_latest_event_type) {
    case "success":
      return "resource-update-panel__notice resource-update-panel__notice--success"
    case "warning":
      return "resource-update-panel__notice resource-update-panel__notice--warning"
    default:
      return "resource-update-panel__notice resource-update-panel__notice--info"
  }
})

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
  return entryKey === "base.enabled_auto_startup" || entryKey === "base.enabled_check_resource_updates"
}

async function refreshDmmPlayerToken() {
  await apis.refresh_ddm_player_token()
  await appStore.load_config()
  await message.showSuccess("启动参数刷新成功")
}

async function checkResourceUpdates() {
  await appStore.check_resource_updates()
}

async function applyResourceUpdates() {
  await appStore.apply_resource_updates()
}

function reset() {
  dialogs.confirm("是否要重置所有设置项", "请谨慎操作，该操作回导致所有设置项恢复默认（包括任务设置）").then(() => {
    appStore.reset_config();
  }).catch(() => {
    console.log("用户取消")
  })
}

const drawerValue = computed({
  get: () => (props.temporary ? props.modelValue : true),
  set: value => emit("update:modelValue", value),
})
</script>

<template>
  <v-navigation-drawer
    v-model="drawerValue"
    :permanent="!temporary"
    :temporary="temporary"
    :scrim="temporary"
    :width="width"
    :class="['settings_drawer', { 'settings_drawer--instant': disableTransition }]"
  >
    <v-card class="settings_drawer__title_card">
      <div class="settings_drawer__title">脚本设置</div>
    </v-card>
    <v-divider/>
    <v-list nav>
      <v-list-item subtitle="基础设置"/>
      <template v-for="entry in settingEntries" :key="entry.key">
        <v-divider v-if="shouldShowDivider(entry.key)" />
        <ConfigAutoField :config="appStore.config" :item="entry.item" />
      </template>
      <v-list-item v-if="showResourceUpdateTools" class="resource-update-list-item">
        <div class="resource-update-panel">
          <div class="resource-update-panel__header">
            <div class="resource-update-panel__header-main">
              <div class="resource-update-panel__title">资源更新</div>
              <div class="resource-update-panel__headline">{{ resourceUpdateHeadline }}</div>
            </div>
            <v-chip
              class="resource-update-panel__state"
              :color="resourceUpdateStateColor"
              variant="tonal"
              size="small"
            >
              {{ resourceUpdateStateLabel }}
            </v-chip>
          </div>
          <div class="resource-update-panel__meta">{{ resourceUpdateStatusText }}</div>
          <div
            v-if="resourceUpdateLastError"
            class="resource-update-panel__notice resource-update-panel__notice--warning"
          >
            最近错误：{{ resourceUpdateLastError }}
          </div>
          <div v-if="appStore.resource_update_latest_event" :class="resourceUpdateNoticeClass">
            {{ appStore.resource_update_latest_event }}
          </div>
          <div class="resource-update-panel__actions">
            <v-btn
              class="resource-update-panel__button"
              variant="outlined"
              prepend-icon="md:manage_search"
              :loading="resourceUpdateBusy && !appStore.resource_update_status?.updating"
              :disabled="resourceUpdateBusy"
              @click="checkResourceUpdates"
            >
              检查更新
            </v-btn>
            <v-btn
              v-if="resourceUpdateHasUpdate"
              class="resource-update-panel__button"
              color="success"
              variant="tonal"
              prepend-icon="md:system_update_alt"
              :loading="Boolean(appStore.resource_update_status?.updating)"
              :disabled="resourceUpdateBusy"
              @click="applyResourceUpdates"
            >
              立即更新
            </v-btn>
          </div>
        </div>
      </v-list-item>
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
      <div class="settings_actions pa-2 mb-2 mt-2">
        <v-btn
          class="settings_actions__button"
          @click="appStore.save_config()"
          color="green"
          append-icon="md:save"
        >
          保存设置
        </v-btn>
        <v-btn
          class="settings_actions__button"
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

<style scoped>
.settings_drawer {
  max-width: 100%;
}

.settings_drawer :deep(.v-navigation-drawer__content) {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.settings_drawer--instant {
  transition: none !important;
}

.settings_drawer--instant :deep(.v-navigation-drawer__content) {
  transition: none !important;
}

.settings_drawer :deep(.v-list) {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}

.settings_drawer__title_card {
  flex: 0 0 auto;
  min-height: 60px;
  display: flex;
  align-items: center;
  padding: 0 16px;
}

.settings_drawer__title {
  font-size: 1.1rem;
  font-weight: 700;
  line-height: 1.2;
  text-align: left;
}

.settings_actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.settings_actions__button {
  flex: 1 1 140px;
  min-width: 0;
}

.resource-update-list-item {
  align-items: stretch;
}

.resource-update-list-item :deep(.v-list-item__content) {
  width: 100%;
}

.resource-update-panel {
  width: 100%;
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.resource-update-panel__header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 12px;
}

.resource-update-panel__header-main {
  flex: 1 1 180px;
  min-width: 0;
}

.resource-update-panel__state {
  flex: 0 0 auto;
  margin-left: auto;
}

.resource-update-panel__title {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.2;
}

.resource-update-panel__headline {
  margin-top: 6px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 13px;
  line-height: 1.45;
}

.resource-update-panel__meta {
  color: rgba(255, 255, 255, 0.86);
  font-size: 13px;
  line-height: 1.5;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.resource-update-panel__notice {
  padding: 10px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.45;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.resource-update-panel__notice--success {
  background: rgba(76, 175, 80, 0.14);
  color: #b9f6ca;
}

.resource-update-panel__notice--warning {
  background: rgba(255, 179, 0, 0.14);
  color: #ffe082;
}

.resource-update-panel__notice--info {
  background: rgba(66, 165, 245, 0.14);
  color: #bbdefb;
}

.resource-update-panel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.resource-update-panel__button {
  flex: 1 1 140px;
  min-width: 0;
}

@media (max-width: 599px) {
  .settings_actions {
    gap: 8px;
  }

  .resource-update-panel {
    padding: 14px;
    gap: 10px;
  }

  .resource-update-panel__header {
    flex-direction: column;
    align-items: stretch;
  }

  .resource-update-panel__state {
    margin-left: 0;
    align-self: flex-start;
  }

  .resource-update-panel__actions {
    gap: 8px;
  }
}
</style>
