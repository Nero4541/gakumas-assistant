class EventBus {
  constructor() {
    this.events = {}
  }
  on(event, handler) {
    if (!this.events[event]) this.events[event] = []
    this.events[event].push(handler)
  }
  off(event, handler) {
    this.events[event] = (this.events[event] || []).filter(h => h !== handler)
  }
  emit(event, data) {
    (this.events[event] || []).forEach(h => h(data))
  }
}

export const eventBus = new EventBus()
