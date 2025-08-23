export default {
  mounted(el, binding) {
    el.__autoSaveHandler__ = (e) => {
      // 如果失焦后焦点不在当前容器内
      if (!el.contains(e.relatedTarget)) {
        const fn = binding.value
        if (typeof fn === "function") {
          fn()
        }
      }
    }
    el.addEventListener("focusout", el.__autoSaveHandler__)
  },
  unmounted(el) {
    el.removeEventListener("focusout", el.__autoSaveHandler__)
    delete el.__autoSaveHandler__
  }
}
