<script setup>
import app from "@/main.js";

const props = defineProps({
  data: Object
})
</script>

<template>
  <base__adb_connect_mode :data="props.data"/>
  <div v-if="props.data.base.adb_connect_mode.value === 'Network'">
    <v-list-item>
      <v-text-field
        label="ADB主机名"
        hint="安卓调试桥的ip地址，模拟器一般是127.0.0.1"
        append-icon="md:replay"
        v-model="props.data.base.adb_host.value"
        @click:append="props.data.base.adb_host.value = props.data.base.adb_host.default_value"
        persistent-hint
      />
    </v-list-item>
    <v-list-item>
      <v-text-field
        label="ADB端口"
        hint="安卓调试桥的端口，默认5555，Android11以上为系统随机"
        type="number"
        append-icon="md:replay"
        v-model="props.data.base.adb_port.value"
        @click:append="props.data.base.adb_port.value = props.data.base.adb_port.default_value"
        persistent-hint
      />
    </v-list-item>
  </div>
  <div v-else>
    <base__adb_devices :data="props.data" :only_usb_device="true" />
  </div>
  <v-list-item>
    <v-select
      label="ADB截图方式"
      hint="DroidCast>ADB"
      :items="['DroidCast', 'ADB']"
      :item-color="app.config.globalProperties.$theme.color"
      v-model="props.data.base.android_screen_capture_service.value"
      persistent-hint
    />
  </v-list-item>
  <v-list-item>
    <v-select
      label="ADB点击屏幕方式"
      hint="部分点击服务可能存在兼容性问题，如遇到问题请回退到ADB"
      :items="['ADB']"
      :item-color="app.config.globalProperties.$theme.color"
      v-model="props.data.base.android_touch_service.value"
      persistent-hint
    />
  </v-list-item>
  <v-list-item>
    <v-text-field
      label="游戏包名"
      hint="默认：com.bandainamcoent.idolmaster_gakuen（修改后需重启生效）"
      append-icon="md:replay"
      v-model="props.data.base.game_package_name.value"
      @click:append="props.data.base.game_package_name.value = props.data.base.game_package_name.default_value"
      persistent-hint
    />
  </v-list-item>
</template>

<style scoped>

</style>
