<template>
  <v-layout class="page_body rounded rounded-md">
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
    <task_list v-if="tabbar_model[0] === 'tasks'"/>
    <settings v-else-if="tabbar_model[0] === 'settings'"/>

    <v-main class="page_main d-flex align-center justify-center">
      <v-container class="page_container">
        <v-alert
          v-if="!store.status.task"
          title="等待操作"
          color="warning"
        />
        <v-alert
          v-else
          title="脚本执行中......"
          color="success"
        />
        <WebSocketToolsBar/>
        <WebSocketView />
      </v-container>
      <WebLogger/>
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
  import {useAppStore} from "@/stores/app.js";
  import app from "@/main.js";
  const store = useAppStore();
  let tabbar_model = ref(["tasks"])
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
      .page_view {
        height: 100%;
        display: flex;
        .web_view {
          width: 100%;
        }
      }
    }
  }
  .page_footer {
    max-height: 50px;
  }
}
</style>
