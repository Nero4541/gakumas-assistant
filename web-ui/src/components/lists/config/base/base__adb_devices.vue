<script setup>
import apis from "@/scripts/apis.js";

const props = defineProps({
  data: Object,
  only_usb_device: {
    type: Boolean,
    default: false,
  }
})

const device = ref([])
const load_status = ref(false)
const load_message = ref("")
const device_hint = computed(() => {
  const baseHint = "请选择通过USB连接的设备，如未找到设备请尝试刷新列表"
  return load_message.value ? `${baseHint}。${load_message.value}` : baseHint
})

function load_device_list() {
  load_status.value = false
  load_message.value = ""
  apis.get_all_adb_device(props.only_usb_device).then((res) => {
    device.value = res.data.devices || []
    load_message.value = res.data.message || ""
    load_status.value = true
  })
}

load_device_list()
</script>

<template>
  <v-list-item>
    <v-select
      :items="device"
      :loading="!load_status"
      v-model="props.data.base.adb_serial.value"
      append-icon="md:replay"
      @click:append="load_device_list"
      clearable
      label="通过USB连接的ADB设备"
      :hint="device_hint"
      persistent-hint
    />
  </v-list-item>
</template>

<style scoped>

</style>
