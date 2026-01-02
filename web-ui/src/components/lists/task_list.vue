<script setup>
import apis from "@/scripts/apis.js";
import auto_purchase_setting from "@/components/lists/config/task_settings/auto_purchase_setting.vue"
import auto_contest_setting from "@/components/lists/config/task_settings/auto_contest_setting.vue";
import dispatch_work_setting from "@/components/lists/config/task_settings/dispatch_work_setting.vue";
import { useAppStore } from "@/stores/app.js";

const app_store = useAppStore();

const settingComponents = {
  auto_purchase: auto_purchase_setting,
  auto_contest: auto_contest_setting,
  dispatch_work: dispatch_work_setting,
}

const statusMap = {
  PENDING: {color: "orange", icon: "md:schedule", label: "等待中"},
  RUNNING: {color: "blue", icon: "md:cached", label: "运行中"},
  SUSPENDED: {color: "yello", icon: "md:hourglass", label: "挂起中"},
  SUCCESS: {color: "green", icon: "md:task_alt", label: "已完成"},
  FAILED: {color: "red", icon: "md:error", label: "执行错误"},
  CANCELED: {color: "grey", icon: "md:cancel", label: "已取消"},
  UNKNOWN: {color: "grey", icon: "md:indeterminate_question_box", label: "未知状态"},
}

function normalizeTimestamp(ts) {
  if (!ts || ts <= 0) return null
  // 如果是秒级（10位），转成毫秒
  if (ts < 1e12) {
    ts = ts * 1000
  }
  return ts
}

function formatAbsoluteTime(ts) {
  const t = normalizeTimestamp(ts)
  if (!t) return "未运行"
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(new Date(t))
}

function formatRelativeTime(ts) {
  if (!ts || ts <= 0) return "未运行"
  ts = normalizeTimestamp(ts)
  const now = Date.now()
  const diff = Math.floor((now - ts) / 1000) // 秒差

  if (diff < 5) return `刚刚`
  if (diff < 60) return `${diff}秒前`
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  if (diff < 172800) return "昨天"
  return `${Math.floor(diff / 86400)}天前`
}
</script>

<template>
  <v-navigation-drawer permanent width="400">
    <v-card title="任务列表" class="pa-3"></v-card>
    <v-divider/>

    <v-expansion-panels variant="accordion">
      <v-expansion-panel
        v-for="(task, task_name) in app_store.task_list"
        :key="task_name"
        elevation="1"
      >
        <v-expansion-panel-title>
          <v-icon
            :color="statusMap[task.status]?.color || 'grey'"
            :icon="statusMap[task.status]?.icon || 'mdi-help-circle'"
            :class="`mr-2 task_${task.status}`"
          />
          <span class="font-medium">{{ task.description }}</span>
          <template v-slot:actions>
            <v-chip
              v-if="task.manual_only"
              size="small"
              class="ml-2">
              仅手动
            </v-chip>
            <v-chip
              size="small"
              :color="statusMap[task.status]?.color"
              text-color="white"
              class="ml-2"
            >
              {{ statusMap[task.status]?.label }}
            </v-chip>
          </template>
        </v-expansion-panel-title>

        <v-expansion-panel-text>
          <div class="pa-2">
            <p class="text-body-2">任务名：<b>{{ task_name }}</b></p>
            <p class="text-body-2">启用：{{ task.enable ? "是" : "否" }}</p>
            <p class="text-body-2">
              上次运行时间：
              <span :title="formatAbsoluteTime(task.last_run_time)">
                {{ formatRelativeTime(task.last_run_time) }}
              </span>
            </p>

            <div class="d-flex mt-3" style="gap: 8px">
              <v-btn
                :disabled="task.status === 'RUNNING'"
                color="primary"
                variant="outlined"
                @click="apis.run_task(task_name)"
              >
                执行
              </v-btn>
              <v-btn
                v-if="task.enable"
                color="red"
                variant="tonal"
                @click="apis.disable_task(task_name)"
              >
                禁用
              </v-btn>
              <v-btn
                v-else
                color="green"
                variant="tonal"
                @click="apis.enable_task(task_name)"
              >
                启用
              </v-btn>
            </div>
          </div>
          <div v-if="settingComponents[task_name]" class="mt-4">
            <h4>任务设置</h4>
            <component
              :is="settingComponents[task_name]"
              :task="task"
              :task_name="task_name"
            />
          </div>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>
  </v-navigation-drawer>
</template>


<style scoped>
.task_tools_bar {
  margin-top: 10px;
  display: flex;

  .v-btn:not(:last-child) {
    margin-right: 5px;
  }
}

.task_RUNNING {
  animation: spinPause 3s linear infinite running;
}

@keyframes spinPause {
  0% {
    transform: rotate(0deg);
  }
  33.3% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}
</style>
