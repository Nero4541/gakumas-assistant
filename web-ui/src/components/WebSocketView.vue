<template>
  <div ref="containerRef" class="websocket_view">
    <canvas ref="canvasRef" class="websocket_view-canvas" />
  </div>
</template>

<script setup>
  import { onMounted, onUnmounted, ref } from 'vue'

  const canvasRef = ref(null)
  const containerRef = ref(null)
  let lastBuffer = null
  let resizeObserver = null

  function parseBinaryData (buffer) {
    const bytes = new Uint8Array(buffer)
    let comma1 = -1, comma2 = -1

    for (const [i, byte] of bytes.entries()) {
      if (byte === 44) {
        if (comma1 === -1) comma1 = i
        else {
          comma2 = i; break
        }
      }
    }

    if (comma1 === -1 || comma2 === -1) throw new Error('无效的格式')

    const width = Number.parseInt(String.fromCodePoint(...bytes.subarray(0, comma1)), 10)
    const height = Number.parseInt(String.fromCodePoint(...bytes.subarray(comma1 + 1, comma2)), 10)
    const imageBytes = bytes.subarray(comma2 + 1)

    return { width, height, imageBytes }
  }

  async function renderToCanvas (buffer) {
    const canvas = canvasRef.value
    const container = containerRef.value
    if (!canvas || !container) return

    const { width, height, imageBytes } = parseBinaryData(buffer)
    const ctx = canvas.getContext('2d')

    const blob = new Blob([imageBytes], { type: 'image/jpeg' })
    const imgUrl = URL.createObjectURL(blob)
    const img = new Image()
    img.src = imgUrl

    await new Promise(resolve => img.addEventListener('load', resolve))

    const dpr = window.devicePixelRatio || 1
    const rect = container.getBoundingClientRect()
    const scale = Math.min(rect.width / width, rect.height / height)

    const newWidth = Math.round(width * scale)
    const newHeight = Math.round(height * scale)

    canvas.width = newWidth * dpr
    canvas.height = newHeight * dpr
    canvas.style.width = `${newWidth}px`
    canvas.style.height = `${newHeight}px`

    ctx.scale(dpr, dpr)
    ctx.imageSmoothingEnabled = false

    const offsetX = (newWidth - width * scale) / 2
    const offsetY = (newHeight - height * scale) / 2

    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, offsetX, offsetY, width * scale, height * scale)

    lastBuffer = buffer
  }

  function connectWebSocket () {
    const socket = new WebSocket('ws://127.0.0.1:8000/ws')
    socket.binaryType = 'arraybuffer'

    socket.onmessage = event => {
      if (event.data instanceof ArrayBuffer) {
        renderToCanvas(event.data)
      }
    }

    socket.addEventListener('close', () => {
      setTimeout(connectWebSocket, 1000) // 自动重连
    })
  }

  onMounted(() => {
    connectWebSocket()

    const container = containerRef.value
    if (!container) return

    resizeObserver = new ResizeObserver(() => {
      if (lastBuffer) {
        renderToCanvas(lastBuffer)
      }
    })
    resizeObserver.observe(container)
  })

  onUnmounted(() => {
    if (resizeObserver) {
      resizeObserver.disconnect()
      resizeObserver = null
    }
  })
</script>

<style scoped>
.websocket_view {
  width: 100%;
  height: 100%;
  overflow: hidden;
  position: relative;
  background: rgb(33,33,33);
}

.websocket_view-canvas {
  display: block;
  margin: 0 auto;
  width: 100%;
  height: 100%;

}
</style>
