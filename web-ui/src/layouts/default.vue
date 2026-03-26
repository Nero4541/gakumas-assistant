<template>
  <v-layout :class="['page_body', { 'page_body--native': isNativeShell }]">
    <v-app-bar
      id="app-bar"
      :height="appBarHeight"
      :color="app.config.globalProperties.$theme.color"
    >
      <div
        class="app_bar__drag_surface pywebview-drag-region"
        @mousedown.left="handleDragSurfaceMouseDown"
        @dblclick.left.prevent="toggleWindowMaximize"
      >
        <div class="app_bar__brand">
          <v-avatar
            :image="app.config.globalProperties.$theme.icon"
            rounded="0"
            :size="appBarAvatarSize"
          />
          <h1>Gakumas Assistant</h1>
        </div>
        <div class="app_bar__fill" />
      </div>
      <div class="app_bar__actions" @dblclick.stop>
        <div v-if="isMobileShell" class="app_bar__mobile_actions">
          <v-btn
            icon="md:format_list_bulleted"
            variant="text"
            color="white"
            @click="openSection('tasks')"
          />
          <v-btn
            icon="md:settings"
            variant="text"
            color="white"
            @click="openSection('settings')"
          />
        </div>
        <PyWebviewWindowControls />
      </div>
    </v-app-bar>

    <v-navigation-drawer v-if="!isMobileShell" permanent rail>
      <v-list density="compact" :selected="tabbar_model" nav :color="app.config.globalProperties.$theme.color">
        <v-list-item
          prepend-icon="md:format_list_bulleted"
          title="任务列表"
          value="tasks"
          @click="openSection('tasks')"
        />
        <v-divider/>
        <v-list-item
          prepend-icon="md:settings"
          title="脚本配置"
          value="settings"
          @click="openSection('settings')"
        />
      </v-list>
    </v-navigation-drawer>
    <TaskList
      v-if="activeSection === 'tasks'"
      v-model="sidePanelOpen"
      :temporary="showOverlayPanel"
      :disable-transition="sidePanelInstantSwap"
      :width="sidePanelWidth"
    />
    <SettingsPanel
      v-else-if="activeSection === 'settings'"
      v-model="sidePanelOpen"
      :temporary="showOverlayPanel"
      :disable-transition="sidePanelInstantSwap"
      :width="sidePanelWidth"
    />

    <v-main class="page_main d-flex align-center justify-center">
      <v-container class="page_container">
        <WebSocketToolsBar/>
        <WebSocketView />
      </v-container>
      <WebLogger/>
    </v-main>
    <AppFooter class="page_footer" />
  </v-layout>
</template>

<script setup>
  import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
  import { useDisplay } from "vuetify";
  import PyWebviewWindowControls from "@/components/PyWebviewWindowControls.vue";
  import TaskList from "@/components/lists/task_list.vue";
  import WebSocketView from "@/components/WebSocketView.vue";
  import WebSocketToolsBar from "@/components/WebSocketToolsBar.vue";
  import SettingsPanel from "@/components/lists/settings.vue";
  import {
    addWindowHostReadyListener,
    getWindowHostApi,
    getWindowHostKind,
    isWindowHostAvailable,
    syncWindowHostShellClass,
  } from "@/scripts/utils/windowHost.js";
  import app from "@/main.js";

  const display = useDisplay();
  const DEFAULT_SECTION = "tasks";
  const WINDOW_DRAG_THRESHOLD = 6;
  const tabbar_model = ref([DEFAULT_SECTION]);
  const sidePanelOpen = ref(false);
  const sidePanelInstantSwap = ref(false);
  const isNativeShell = ref(false);
  const isPywebviewShell = ref(false);
  const pendingWindowDrag = {
    active: false,
    startX: 0,
    startY: 0,
  };
  let removeWindowHostReadyListener = null;

  const activeSection = computed(() => tabbar_model.value[0] || DEFAULT_SECTION);
  const isMobileShell = computed(() => display.smAndDown.value);
  const showOverlayPanel = computed(() => isMobileShell.value || display.width.value < 1400);
  const appBarHeight = computed(() => (isMobileShell.value ? 72 : 80));
  const appBarAvatarSize = computed(() => (isMobileShell.value ? 56 : 80));
  const sidePanelWidth = computed(() => {
    const width = display.width.value;

    if (isMobileShell.value) {
      return Math.max(240, Math.min(420, width - 24));
    }

    if (showOverlayPanel.value) {
      return Math.max(300, Math.min(400, width - 120));
    }

    return 400;
  });

  watch(showOverlayPanel, value => {
    sidePanelOpen.value = !value;
  }, { immediate: true });

  async function openSection(section) {
    const sameSection = activeSection.value === section;
    if (!showOverlayPanel.value) {
      tabbar_model.value = [section];
      return;
    }

    if (sameSection) {
      sidePanelOpen.value = !sidePanelOpen.value;
      return;
    }

    if (sidePanelOpen.value) {
      sidePanelInstantSwap.value = true;
      tabbar_model.value = [section];
      await nextTick();
      window.requestAnimationFrame(() => {
        sidePanelInstantSwap.value = false;
      });
      return;
    }

    tabbar_model.value = [section];
    await nextTick();
    window.requestAnimationFrame(() => {
      sidePanelOpen.value = true;
    });
  }

  function syncNativeShellState() {
    const nativeShell = isWindowHostAvailable();
    isNativeShell.value = nativeShell;
    isPywebviewShell.value = getWindowHostKind() === "pywebview";
    syncWindowHostShellClass();
  }

  function clearPendingWindowDrag() {
    pendingWindowDrag.active = false;
    window.removeEventListener("mousemove", handleWindowDragMouseMove);
    window.removeEventListener("mouseup", clearPendingWindowDrag);
  }

  function handleWindowDragMouseMove(event) {
    if (!pendingWindowDrag.active) {
      return;
    }

    if ((event.buttons & 1) === 0) {
      clearPendingWindowDrag();
      return;
    }

    const deltaX = Math.abs(event.clientX - pendingWindowDrag.startX);
    const deltaY = Math.abs(event.clientY - pendingWindowDrag.startY);

    if (deltaX < WINDOW_DRAG_THRESHOLD && deltaY < WINDOW_DRAG_THRESHOLD) {
      return;
    }

    clearPendingWindowDrag();
    getWindowHostApi()?.start_window_drag?.();
  }

  function handleDragSurfaceMouseDown(event) {
    if (isPywebviewShell.value) {
      return;
    }
    event.preventDefault();
    pendingWindowDrag.active = true;
    pendingWindowDrag.startX = event.clientX;
    pendingWindowDrag.startY = event.clientY;

    window.addEventListener("mousemove", handleWindowDragMouseMove);
    window.addEventListener("mouseup", clearPendingWindowDrag);
  }

  function toggleWindowMaximize() {
    clearPendingWindowDrag();
    getWindowHostApi()?.toggle_maximize_window?.();
  }

  onMounted(() => {
    syncNativeShellState();
    removeWindowHostReadyListener = addWindowHostReadyListener(syncNativeShellState);
  });

  onBeforeUnmount(() => {
    clearPendingWindowDrag();
    removeWindowHostReadyListener?.();
    removeWindowHostReadyListener = null;
    document.documentElement.classList.remove("window-host-shell");
    document.body.classList.remove("window-host-shell");
    document.documentElement.classList.remove("pywebview-shell");
    document.body.classList.remove("pywebview-shell");
  });
</script>

<style scoped lang="scss">
#app-bar {
  padding-inline: 15px;
  overflow: hidden;
  border-top-left-radius: inherit;
  border-top-right-radius: inherit;

  :deep(.v-toolbar__content) {
    min-width: 0;
    padding-inline: 0 !important;
    gap: 12px;
  }
}

.app_bar__brand {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;

  h1 {
    color: white;
    font-size: clamp(1.25rem, 2vw, 2rem);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.app_bar__drag_surface {
  flex: 1 1 auto;
  min-width: 0;
  height: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  user-select: none;
  -webkit-user-select: none;
}

.app_bar__fill {
  flex: 1 1 auto;
  min-width: 0;
  height: 100%;
}

.app_bar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}

.app_bar__mobile_actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.page_body {
  position: relative;
  width: 100%;
  min-height: 100dvh;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: 20px;
  //background: rgb(var(--v-theme-background));

  .page_main {
    flex: 1 1 auto;
    min-height: 0;
    position: relative;
    overflow: hidden;
    align-items: stretch !important;
    justify-content: flex-start !important;

    .page_container {
      flex: 1 1 0;
      width: auto;
      max-width: none;
      align-self: stretch;
      min-width: 0;
      min-height: 0;
      display: flex;
      flex-direction: column;
      padding: 16px;

      :deep(.v-alert) {
        padding: 25px 15px;
      }
    }
  }

  .page_footer {
    flex: 0 0 auto;
  }
}

//.page_body--native {
//  border-radius: 0;
//}

@media (max-width: 959px) {
  #app-bar {
    padding-inline: 12px;
  }

  .page_body {
    .page_main {
      .page_container {
        padding: 12px;
      }
    }
  }
}

@media (max-width: 599px) {
  .app_bar__brand {
    gap: 10px;

    h1 {
      font-size: 1.15rem;
    }
  }

  .app_bar__actions {
    gap: 6px;
  }
}
</style>
