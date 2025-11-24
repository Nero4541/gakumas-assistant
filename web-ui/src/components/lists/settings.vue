<script setup>
import apis from "@/scripts/apis.js";
import message from "@/scripts/utils/message.js";
import Base__disabled_task_list from "@/components/lists/config/base/base__disabled_task_list.vue";
import app from "@/main.js";
import dialogs from "@/scripts/utils/dialogs.js";

const props = defineProps({
  data: Object
})

function save() {
  apis.save_config(props.data).then((response) => {
    props.data = response.data
    message.showSuccess("设置保存成功，部分设置可能需要重启生效")
  })
}
function reset() {
  dialogs.confirm("是否要重置所有设置项", "请谨慎操作，该操作回导致所有设置项恢复默认（包括任务设置）").then(() => {
    apis.reset_config().then(response => {
      props.data = response.data
      message.showSuccess("设置重置完成，部分设置可能需要重启生效")
    })
  }).catch((err) => {
    console.log("用户取消")
  })
}
</script>

<template>
  <v-navigation-drawer permanent width="400">
    <v-card title="脚本设置" class="pa-3"></v-card>
    <v-divider/>
    <v-list nav>
      <v-list-item subtitle="基础设置"/>
      <base__run_mode :data="props.data"/>
      <v-list-item>
        <v-switch
          v-model="props.data.base.auto_start_game.value"
          label="自动启动游戏"
          hint="当游戏未启动时是否自动启动游戏"
          persistent-hint
        />
      </v-list-item>
      <base__pc :data="props.data" v-if="props.data.base.run_mode.value === 'PC'"/>
      <base__phone :data="props.data" v-if="props.data.base.run_mode.value === 'Phone'"/>
      <base__disabled_task_list :data="props.data"/>
      <v-divider/>
      <v-list-item>
        <v-switch
          label="每日自动执行脚本"
          hint="未实现"
          :color="app.config.globalProperties.$theme.color"
          persistent-hint
          v-model="props.data.base.enabled_auto_startup.value"
        />
      </v-list-item>
      <v-list-item>
        <v-text-field
          v-model="props.data.base.auto_startup_time.value"
          label="自动运行触发时间"
          readonly
        >
          <v-menu
            :close-on-content-click="false"
            activator="parent"
            min-width="0"
          >
            <v-time-picker v-model="props.data.base.auto_startup_time.value" format="24hr"></v-time-picker>
          </v-menu>
        </v-text-field>
      </v-list-item>
    </v-list>
    <template v-slot:append>
      <div class="pa-2 mb-2 mt-2">
        <v-btn
          class="mr-2"
          @click="save()"
          color="green"
          append-icon="md:save"
        >
          保存设置
        </v-btn>
        <v-btn
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
</style>
