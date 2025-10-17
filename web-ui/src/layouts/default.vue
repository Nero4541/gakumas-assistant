<template>
  <v-layout class="page_body rounded rounded-md">
<!--    <v-system-bar window color="white">-->
<!--      <v-icon>mdi-minus</v-icon>-->
<!--      <v-icon class="ms-2">mdi-checkbox-blank-outline</v-icon>-->
<!--      <v-icon class="ms-2">mdi-close</v-icon>-->
<!--    </v-system-bar>-->
    <v-app-bar
      id="app-bar"
      height="80"
      :color="app.config.globalProperties.$theme.color"
    >
      <v-avatar :image="app.config.globalProperties.$theme.icon" rounded="0" size="80"/>
      <h1>Gakumas Assistant</h1>
    </v-app-bar>

    <v-navigation-drawer permanent rail>
      <v-list density="compact" v-model:selected="tabbar_model" nav :color="app.config.globalProperties.$theme.color">
        <v-list-item
          prepend-icon="md:format_list_bulleted"
          title="任务列表"
          value="tasks"
        />
        <v-divider/>
        <v-list-item
          prepend-icon="md:settings"
          title="脚本配置"
          value="settings"
        />
      </v-list>
    </v-navigation-drawer>
    <task_list v-if="tabbar_model[0] === 'tasks'" :data="task_list"/>
    <settings v-else-if="tabbar_model[0] === 'settings'" :data="config_data"/>

    <v-main class="page_main d-flex align-center justify-center">
      <v-container class="page_container">
        <v-alert
          v-if="!status.task"
          title="等待操作"
          color="warning"
        />
        <v-alert
          v-else
          title="脚本执行中......"
          color="success"
        />
        <WebSocketToolsBar :status="status"/>
        <WebSocketView />
      </v-container>
    </v-main>
    <AppFooter class="page_footer" />
  </v-layout>
</template>

<script setup>
  import Task_list from "@/components/lists/task_list.vue";
  import api from "@/scripts/apis.js"
  import WebSocketView from "@/components/WebSocketView.vue";
  import WebSocketToolsBar from "@/components/WebSocketToolsBar.vue";
  import Settings from "@/components/lists/settings.vue";
  import app from "@/main.js";
  let status = ref({})
  let task_list = ref({})
  let config_data = ref({})
  let tabbar_model = ref(["tasks"])
  async function get_data() {
    try {
      const [statusRes, taskRes] = await Promise.all([
        api.get_status(),
        api.get_registered_tasks()
      ])
      status.value = statusRes.data
      task_list.value = taskRes.data
    } catch (err) {
      console.error("请求出错:", err)
    } finally {
      setTimeout(get_data, 1000)
    }
  }
  get_data()
  api.get_config().then(res => {
    config_data.value = res.data
  })

  let WebSocketManager = {
    socket: null,
    status: false,
  }

  function connectWebSocket () {
    if (WebSocketManager.status) {
      WebSocketManager.socket.close()
      WebSocketManager.socket = null
      WebSocketManager.status = false
    }
    // drawPlaceholder('连接中......')

    WebSocketManager.socket = new WebSocket(`ws://${location.host}/ws`)
    WebSocketManager.socket.binaryType = 'arraybuffer'

    socket.onmessage = event => {
      if (event.data instanceof ArrayBuffer) {
        renderToCanvas(event.data)
      }
    }

    socket.onopen = () => {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    socket.onerror = () => {
      socket.close()
    }

    socket.onclose = () => {
      drawPlaceholder('正在重建连接......')
      reconnectTimer = setTimeout(connectWebSocket, 1000)
    }
  }
</script>

<style scoped lang="scss">
#app-bar {
  padding-left: 15px;
  padding-right: 15px;
  h1 {
    color: white;
  }
}
.page_body {
  width: 100vw;
  height: 100vh;
  //margin: 5vh auto;
  display: flex;
  flex-direction: column;
  //border-radius: 30px !important;
  overflow: hidden;
  box-shadow: 0 0 12px rgba(0, 0, 0, 0.15);
  .page_main {
    flex: 1;
    height: 100%;
    .page_container {
      height: 100%;
      display: flex;
      flex-direction: column;
      .v-alert {
        padding: 25px 15px;
      }
    }
  }
  .page_footer {
    max-height: 50px;
  }
}
</style>
