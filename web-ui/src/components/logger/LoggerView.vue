<template>
  <div
    class="log-container"
  >
    <v-virtual-scroll
      ref="scroll"
      :items="logs"
      item-height="24"
      @scroll.passive="onScroll"
    >
      <template v-slot:default="{ item }">
        <div
          class="log-line"
          :class="logClass(item)"
        >
          {{ item }}
        </div>
      </template>
    </v-virtual-scroll>
  </div>
</template>

<script setup>
const props = defineProps({
  auto_scroll: {
    type: Boolean,
    default: false,
  }
})

const logs = ref([
  "[INFO] 系统启动完成",
  "[DEBUG] 数据库初始化成功",
  "[WARN] 网络连接不稳定",
  "[ERROR] 无法连接服务器",
  "[INFO] 后台任务已启动",
]);

const logClass = (line) => {
  if (line.includes("ERROR")) return "log-error";
  if (line.includes("WARN")) return "log-warn";
  if (line.includes("DEBUG")) return "log-debug";
  return "log-info";
};

const scroll = ref();
const isAtBottom = ref(true);

function onScroll(e) {
  const el = e.target;
  const diff = el.scrollHeight - el.scrollTop - el.clientHeight;
  isAtBottom.value = diff < 40;
}

watch([() => logs.value.length, () => props.auto_scroll], async () => {
  if (!props.auto_scroll) return;
  await nextTick();
  // if (!isAtBottom.value) return;
  const el = scroll.value.$el;
  if (el) el.scrollTop = el.scrollHeight;
});


// watch(() => logs.value.length, async () => {
//   await nextTick();
//   const el = scroll.value?.$el;
//   if (el) el.scrollTop = el.scrollHeight;
// });

// 模拟日志流入
setInterval(() => {
  logs.value.push(`[${new Date().toLocaleTimeString()}] 日志行 ${logs.value.length + 1}`);
  // if (logs.value.length > 200) logs.value.shift(); // 保持有限长度
}, 100);
</script>

<style scoped>
.v-virtual-scroll {
  color: #ccc;
  border-radius: 8px;
}

.log-container {
  display: flex;
  height: 100%;
  padding: 15px 0;
  background-color: #1e1e1e;
  border-radius: 8px;
}

.log-line {
  white-space: pre;
  line-height: 1.5em;
  padding: 2px 4px;
  transition: background-color 0.2s;
}

.log-line:hover {
  background-color: rgba(255, 255, 255, 0.05);
}

.log-info {
  color: #9cdcfe;
}

.log-debug {
  color: #6a9955;
}

.log-warn {
  color: #dcdcaa;
}

.log-error {
  color: #f44747;
}
</style>
