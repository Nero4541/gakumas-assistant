<template>
  <div class="text-center">
    <v-snackbar
      location="top"
      :multi-line="true"
      timer="white"
      v-model="snackbar"
      :timeout="timeout"
      :color="get_type(type)"
    >
      {{ text }}

      <template v-slot:actions>
        <v-btn
          color="white"
          icon="mdi-window-close"
          variant="text"
          @click="snackbar = false"
        />
      </template>
    </v-snackbar>
  </div>
</template>

<script>
export default {
  props: {
    text: {
      type: String,
      required: true
    },
    timeout: {
      type: Number,
      required: false,
      default: 3000
    },
    type: {
      type: String,
      required: false,
      default: 'success'
    }
  },
  data: () => ({
    snackbar: true,
  }),
  methods: {
    get_type(type) {
      switch (type) {
        case 'success':
          return 'green'
        case 'warning':
          return 'yellow'
        case 'error':
          return 'red'
        case 'info':
          return 'primary'
        default:
          return undefined
      }
    }
  }
}
</script>
