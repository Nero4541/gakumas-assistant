<script setup>
import apis from "@/scripts/apis.js";
import message from "@/scripts/utils/message.js";

const props = defineProps({
  data: Object
})
</script>

<template>
  <v-list-item>
    <v-text-field
      label="游戏窗口名"
      hint="默认：gakumas（修改后需重启生效）"
      append-icon="md:replay"
      v-model="props.data.base.game_window_name.value"
      @click:append="props.data.base.game_window_name.value = props.data.base.game_window_name.default_value"
      persistent-hint
    />
  </v-list-item>
  <v-list-item>
    <v-text-field
      label="游戏安装目录"
      hint="游戏安装路径，指向gakumas.exe（默认自动获取，非必要无需修改）"
      v-model="props.data.dmm_player.game_exe_path.value"
      persistent-hint
    />
  </v-list-item>
  <v-list-item>
    <v-text-field
      label="Viewer ID"
      hint="自动获取，非必要无需修改"
      v-model="props.data.dmm_player.viewer_id.value"
      persistent-hint
      disabled
    />
  </v-list-item>
  <v-list-item>
    <v-text-field
      label="Open ID"
      hint="自动获取，非必要无需修改"
      v-model="props.data.dmm_player.open_id.value"
      persistent-hint
      disabled
    />
  </v-list-item>
  <v-list-item>
    <v-text-field
      label="PF Token"
      hint="自动获取，非必要无需修改"
      v-model="props.data.dmm_player.pf_token.value"
      persistent-hint
      disabled
    />
  </v-list-item>
  <v-list-item>
    <v-btn
      block
      append-icon="md:refresh"
      @click="async ()=> {
        await apis.refresh_ddm_player_token()
        props.data = (await apis.get_config()).data
        message.showSuccess('启动参数刷新成功')
      }">
      刷新启动参数
    </v-btn>
  </v-list-item>
</template>

<style scoped>

</style>
