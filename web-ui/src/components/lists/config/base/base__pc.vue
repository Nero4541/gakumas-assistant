<script setup>
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
</template>

<style scoped>

</style>
