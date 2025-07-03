<template>
  <v-footer
    app
    height="60"
  >
    <div
      class="text-caption text-disabled"
      style="position: absolute; right: 16px;"
    >
      &copy; 2020-{{ (new Date()).getFullYear() }} <span class="d-none d-sm-inline-block">Pigeon Server Team</span>
      —
      <a
        class="text-decoration-none on-surface"
        href="https://github.com/Pigeon-Server/gakumas-assistant/"
        rel="noopener noreferrer"
        target="_blank"
      >
        GPLv3 License
      </a>
    </div>
  </v-footer>
</template>

<script setup>
</script>

<style scoped lang="sass">
  .social-link :deep(.v-icon)
    color: rgba(var(--v-theme-on-background), var(--v-disabled-opacity))
    text-decoration: none
    transition: .2s ease-in-out

    &:hover
      color: rgba(25, 118, 210, 1)
</style>
