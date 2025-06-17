<template>
  <v-layout class="page_body rounded rounded-md">
    <v-app-bar color="rgb(243,142,61)" title="《学园偶像大师》小助手(Gakumas Assistant)" />

    <task_list :data="task_list"/>

    <v-navigation-drawer location="right">
      <v-list nav>
        <v-list-item title="脚本设置" />
      </v-list>
    </v-navigation-drawer>

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
        <WebSocketToolsBar />
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
  let status = ref({})
  let task_list = ref({})
  function get_data() {
    api.get_status().then(res => {
      status.value = res.data
    })
    api.get_registered_tasks().then(res => {
      task_list.value = res.data
    })
    setTimeout(get_data, 1000)
  }
  get_data()
</script>

<style scoped lang="scss">
.page_body {
  width: 80vw;
  height: 85vh;
  margin: 5vh auto;
  display: flex;
  flex-direction: column;
  border-radius: 30px !important;
  overflow: hidden;
  box-shadow: 0 0 12px rgba(0, 0, 0, 0.15);
  .page_main {
    flex: 1;
    height: 100%;
    .page_container {
      height: 100%;
      display: flex;
      flex-direction: column;
    }
  }
  .page_footer {
    max-height: 50px;
  }
}
</style>
