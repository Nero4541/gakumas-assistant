import { createApp } from 'vue'
import inputDialog from '@/components/dialogs/inputDialogV2.vue'
import Vue from '@/main'
import vuetify from '@/plugins/vuetify'

function test () {
  const ConfirmConstructor = Vue.extend(inputOTP)
  const instance = new ConfirmConstructor().$mount()
  document.body.append(instance.$el)

  Vue.prototype.$showInputBox = options => {
    Object.assign(instance, options)
    instance.init()
  }
}

async function init_Dialog (component, other_data = {}) {
  return new Promise((resolve, reject) => {
    const mountNode = document.createElement('div')
    let dialogApp = createApp(component, {
      close: () => {
        if (dialogApp) {
          dialogApp.unmount()
          mountNode.remove()
          dialogApp = undefined
          reject('close')
        }
      },
      confirm: res => {
        resolve(res)
        dialogApp?.unmount()
        mountNode.remove()
        dialogApp = undefined
      },
      ...other_data }).use(vuetify)
    document.body.append(mountNode)
    dialogApp.mount(mountNode)
  })
}

async function showInput_Dialog (title = '', label = '', hint = '', type = 'text', persistent = null, value = null, max = null, min = null) {
  /**
   * 展示输入框
   * @param title 输入框模态标题
   * @param label 输入框内部标题
   * @param hint 输入框提示
   * @param type 输入框类型
   * @param value 输入框值
   * @param max 输入框最大值(仅text与number)
   * @param min 输入框最小值(仅text与number)
   */
  return init_Dialog(inputDialog, {
    title,
    label,
    hint,
    type,
    persistent,
    default_value: value,
    max,
    min,
  })
}

function confirm (title, text, level = 'info', buttons = null, cardOptions = null, dialogOptions = null) {
  return Vue.config.globalProperties.$dialog.create({
    title,
    text,
    level,
    buttons: buttons
      ? buttons
      : [
          { title: '确认', key: true },
          { title: '取消', key: false },
        ],
    cardOptions: cardOptions ?? {
      // any v-card api options
    },
    dialogOptions: dialogOptions ?? {
          maxWidth: '400px',
        },
  })
}

export default {
  init_Dialog,
  confirm,
  inputDialog,
  showInput_Dialog,
}
