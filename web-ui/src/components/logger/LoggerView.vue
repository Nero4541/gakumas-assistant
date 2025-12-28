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
import {wsService} from "@/scripts/utils/websocket.js";
import {WS_ACTION} from "@/scripts/constants.ts";

const props = defineProps({
  auto_scroll: {
    type: Boolean,
    default: false,
  }
})

const logs = ref([]);

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

wsService.on(WS_ACTION.BroadcastLog, data => {
  logs.value.push(data.message);
})
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
