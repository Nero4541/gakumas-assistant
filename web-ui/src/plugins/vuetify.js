/**
 * plugins/vuetify.js
 *
 * Framework documentation: https://vuetifyjs.com`
 */

// Composables
import { createVuetify } from 'vuetify'
import { md3 } from 'vuetify/blueprints'

import { md } from 'vuetify/iconsets/md'
// Locale
import { zhHans } from 'vuetify/locale'
// Styles
import 'vuetify/styles'
// Icon
import 'material-design-icons-iconfont/dist/material-design-icons.css'
import '@mdi/font/css/materialdesignicons.css'
import { aliases, mdi } from "vuetify/iconsets/mdi";


// https://vuetifyjs.com/en/introduction/why-vuetify/#feature-guides
export default createVuetify({
  theme: {
    defaultTheme: 'dark',
    themes: {
      dark: {
        colors: {
          // 默认 info 是灰色，覆盖为蓝色
          info: '#2196F3',
        },
      },
    },
  },
  blueprint: md3,
  locale: {
    locale: 'zhHans',
    messages: { zhHans },
  },
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: {
      mdi,
      md,
    },
  },
})
