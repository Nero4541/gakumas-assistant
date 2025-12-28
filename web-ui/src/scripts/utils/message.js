import dialog_utils from '@/scripts/utils/dialogs.js'
import message_component from '@/components/dialogs/message.vue'

function showApiErrorMsg (message, status = null, close_delay = 3000) {
  /**
   * 显示API错误信息
   */
  return dialog_utils.init_Dialog(message_component, {
    text: `API错误：${message} ${status ? '(status:' + status + ')' : ''}`,
    type: 'error',
    timeout: close_delay,
  })
}

function showSuccess (message, close_delay = 3000) {
  /**
   * 显示成功信息
   */
  return dialog_utils.init_Dialog(message_component, {
    text: message,
    type: 'success',
    timeout: close_delay,
  })
}

function showInfo (message, close_delay = 3000) {
  /**
   * 显示信息
   */
  return dialog_utils.init_Dialog(message_component, {
    text: message,
    type: 'info',
    timeout: close_delay,
  })
}

function showWarning (message, close_delay = 3000) {
  /**
   * 显示警告信息
   */
  return dialog_utils.init_Dialog(message_component, {
    text: message,
    type: 'warning',
    timeout: close_delay,
  })
}

function showError (message, close_delay = 3000) {
  /**
   * 显示错误信息
   */
  return dialog_utils.init_Dialog(message_component, {
    text: message,
    type: 'error',
    timeout: close_delay,
  })
}

export default {
  showApiErrorMsg,
  showSuccess,
  showInfo,
  showWarning,
  showError,
}
