<template>
  <div class="layout">
    <button class="open_web_logger" @click="open = !open" :title="open ? '关闭日志' : '打开日志'">
      <v-icon>{{ open ? 'md:arrow_right' : 'md:arrow_left' }}</v-icon>
    </button>

    <transition name="slide">
      <div v-show="open" class="logger_panel">
        <div class="logger_header">
          <div class="left">
            <span class="title">执行日志</span>
          </div>
        </div>
        <div ref="termContainer" class="term-container"/>
      </div>
    </transition>
  </div>
</template>

<script setup>
import {ref, onMounted, onBeforeUnmount, watch, nextTick} from 'vue';
import {Terminal} from 'xterm';
import {FitAddon} from 'xterm-addon-fit';
import {SearchAddon} from 'xterm-addon-search';
import 'xterm/css/xterm.css';

import {wsService} from '@/scripts/utils/websocket.js';
import {WS_ACTION} from '@/scripts/constants.ts';

const open = ref(false);
const paused = ref(false);
const buffer = ref([]);

let term = null;
let fitAddon = null;
let searchAddon = null;
const termContainer = ref(null);

// 最多保留多少行
const MAX_LINES = 20000;

const LEVEL_COLOR = {
  DEBUG: '\x1b[38;5;244m', // 灰
  INFO: '\x1b[38;5;39m',  // 蓝
  WARN: '\x1b[38;5;214m', // 橙
  ERROR: '\x1b[38;5;196m'  // 红
};

const RESET = '\x1b[0m';

function formatRecord(record) {
  const time = record.time ?? '';
  const level = record.level ?? 'INFO';
  const message = record.message ?? '';

  const color = LEVEL_COLOR[level] || '';

  return (
    `${time}` +
    `${color}[${level}]${RESET} ` +
    `${message}`
  );
}

function flushBuffer() {
  if (!buffer.value.length) return;

  for (const record of buffer.value) {
    term.writeln(formatRecord(record));
  }
  buffer.value = [];
}

function onIncomingLog(record) {
  if (!record) return;

  const line = formatRecord(record);

  if (paused.value) {
    buffer.value.push(record);
    return;
  }

  term.writeln(line);
}

function fitTerminal() {
  nextTick(() => {
    try {
      fitAddon.fit();
    } catch (e) { /* ignore */
    }
  });
}

onMounted(() => {
  term = new Terminal({
    convertEol: true,
    scrollback: MAX_LINES,
    disableStdin: true,
  });
  fitAddon = new FitAddon();
  searchAddon = new SearchAddon();
  term.loadAddon(fitAddon);
  term.loadAddon(searchAddon);
  term.open(termContainer.value);
  fitAddon.fit();

  wsService.on(WS_ACTION.BroadcastLog, record => {
    onIncomingLog(record);
  });

  window.addEventListener('resize', fitTerminal);

  watch(open, async (v) => {
    if (v) {
      await nextTick();
      // 等动画结束
      setTimeout(() => fitAddon.fit(), 260);
    }
  });

  // 定时 flush 本地 buffer（如果 paused=false，这将把缓存排空并写入 terminal）
  const t = setInterval(() => {
    if (!paused.value) flushBuffer();
  }, 200);

  onBeforeUnmount(() => {
    clearInterval(t);
    window.removeEventListener('resize', fitTerminal);
    try {
      term.dispose();
    } catch (e) {
    }
  });
});
</script>

<style scoped>
.layout {
  display: flex;
  align-items: center;
  position: relative;
  height: 100%;
}

.logger_panel {
  width: 480px;
  height: 100%;
  position: relative;
  background: #1e1e1e;
  color: #e0e0e0;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;

  .logger_header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    border-bottom: 1px solid #444;

    .left {
      display: flex;
      align-items: center;
      gap: 12px;

      .title {
        margin: 15px 0 15px 5px;
        font-weight: 700;
        font-size: 20px
      }
    }
  }
}

.term-container {
  flex: 1 1 auto;
  padding: 8px;
  background: #1b1b1b;
  border-radius: 6px;
  margin: 10px;
  overflow: hidden;
}

.open_web_logger {
  background: rgba(255, 255, 255, 0.08);
  border: none;
  cursor: pointer;
  font-size: 18px;
  padding: 6px 6px;
  border-radius: 8px 0 0 8px;
  transition: all 0.2s ease;
  position: absolute;
  left: -36px;
  z-index: 2;
}

.slide-enter-active, .slide-leave-active {
  transition: all 0.25s ease;
}

.slide-enter-from, .slide-leave-to {
  width: 0;
  opacity: 0;
}
</style>
