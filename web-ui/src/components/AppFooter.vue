<template>
  <v-footer
    app
    class="app-footer"
  >
    <div class="app-footer__meta text-caption text-disabled">
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
  .app-footer
    min-height: 48px !important
    height: auto !important
    padding: 8px 16px
    justify-content: flex-end

  .app-footer__meta
    width: 100%
    text-align: right
    line-height: 1.4

  @media (max-width: 959px)
    .app-footer
      padding: 8px 12px

    .app-footer__meta
      text-align: center

  .social-link :deep(.v-icon)
    color: rgba(var(--v-theme-on-background), var(--v-disabled-opacity))
    text-decoration: none
    transition: .2s ease-in-out

    &:hover
      color: rgba(25, 118, 210, 1)
</style>
