/**
 * plugins/vuetify.js
 *
 * Framework documentation: https://vuetifyjs.com`
 */

// Composables
import { createVuetify } from 'vuetify'
import { md3 } from 'vuetify/blueprints'

import { aliases } from 'vuetify/iconsets/fa'
import { md } from 'vuetify/iconsets/md'
// Locale
import { zhHans } from 'vuetify/locale'
// Styles
import 'vuetify/styles'
// Icon
import 'material-design-icons-iconfont/dist/material-design-icons.css'
import '@mdi/font/css/materialdesignicons.css'
import {mdi} from "vuetify/iconsets/mdi";


// https://vuetifyjs.com/en/introduction/why-vuetify/#feature-guides
export default createVuetify({
  theme: {
    defaultTheme: 'dark',
  },
  blueprint: md3,
  locale: {
    locale: 'zhHans',
    message: { zhHans },
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
