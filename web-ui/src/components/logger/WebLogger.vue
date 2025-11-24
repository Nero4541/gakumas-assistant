<script setup>
const open = ref(false);
const auto_scroll = ref(false);
</script>

<template>
  <div class="layout">
    <button class="open_web_logger" @click="open = !open" title="执行日志">
      <v-icon>{{ open ? 'md:arrow_right' : 'md:arrow_left' }}</v-icon>
    </button>
    <transition name="slide">
      <div v-show="open" class="logger_panel">
        <div class="logger_header">
          <span>执行日志</span>
          <v-switch v-model="auto_scroll" label="自动滚动"/>
        </div>
        <logger-view :auto_scroll="auto_scroll" />
      </div>
    </transition>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  align-items: center;
  position: relative;
  height: 100%;
}

.logger_panel {
  width: 360px;
  height: 100%;
  position: relative;
  background: #1e1e1e;
  color: #e0e0e0;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.logger_header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 12px;
  border-bottom: 1px solid #444;
  font-weight: bold;
  font-size: 20px;
}

.open_web_logger {
  background: rgba(255, 255, 255, 0.3);
  border: none;
  cursor: pointer;
  font-size: 18px;
  padding: 5px 3px;
  border-radius: 8px 0 0 8px;
  transition: all 0.3s ease;
  position: absolute;
  left: -30px;
  z-index: 1;
}

.log_item {
  border-bottom: 1px solid #2a2a2a;
  padding: 4px 0;
}

/* 动画（从右向左滑出） */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  width: 0;
  opacity: 0;
}
</style>
