/**
 * main.js
 *
 * Bootstraps Vuetify and other plugins then mounts the App`
 */

// Plugins
import { registerPlugins } from '@/plugins'

// Components
import App from './App.vue'

// Composables
import { createApp } from 'vue'

// Styles
import 'unfonts.css'
import {getRandomTheme} from "@/scripts/utils/theme.js";

const app = createApp(App)

registerPlugins(app)

const theme = getRandomTheme()
app.config.globalProperties.$theme = theme

app.mount('#app')

export default app
