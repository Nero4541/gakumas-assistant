<script>
export default {
  name: 'InputDialog',
  props: {
    title: {
      type: String,
      required: true,
    },
    description: {
      type: String,
      required: true,
    },
    persistent: {
      type: Boolean,
      required: false,
      default: null,
    },
    confirm: {
      type: Function,
      required: true,
    },
    confirm_text: {
      type: String,
      required: false,
      default: '确认',
    },
    close: {
      type: Function,
      required: true,
    },
    close_text: {
      type: String,
      required: false,
      default: '取消',
    }
  },
  data () {
    return {
      flag: true,
    }
  }
}
</script>

<template>
  <v-dialog
    v-model="flag"
    activator="parent"
    :persistent="persistent"
    width="calc(100vw - 24px)"
    max-width="400"
    @close="close()"
  >
    <v-card>
      <v-card-title>{{ title }}</v-card-title>
      <v-card-text>
        {{ description }}
      </v-card-text>
      <v-card-actions>
        <v-btn color="success" @click="confirm()">{{confirm_text}}</v-btn>
        <v-btn color="error" @click="close()">{{close_text}}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>

</style>
