<template>
  <div ref="containerRef" class="websocket_view">
    <canvas ref="canvasRef" class="websocket_view-canvas" />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { wsService } from '@/scripts/utils/websocket.ts'

const canvasRef = ref(null)
const containerRef = ref(null)
let lastBuffer = null
let resizeObserver = null
let currentImgUrl = null

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

  // 释放上一次 blob url
  if (currentImgUrl) {
    URL.revokeObjectURL(currentImgUrl)
    currentImgUrl = null
  }

  const blob = new Blob([imageBytes], { type: 'image/jpeg' })
  currentImgUrl = URL.createObjectURL(blob)

  const img = new Image()
  img.src = currentImgUrl

  await new Promise(resolve => img.addEventListener('load', resolve, { once: true }))

  const dpr = window.devicePixelRatio || 1
  const rect = container.getBoundingClientRect()
  const scale = Math.min(rect.width / width, rect.height / height)

  const newWidth = Math.round(width * scale)
  const newHeight = Math.round(height * scale)

  canvas.width = newWidth * dpr
  canvas.height = newHeight * dpr
  canvas.style.width = `${newWidth}px`
  canvas.style.height = `${newHeight}px`

  // 重置 transform 避免 scale 累积
  ctx.setTransform(1, 0, 0, 1, 0, 0)
  ctx.scale(dpr, dpr)
  ctx.imageSmoothingEnabled = false

  const offsetX = (newWidth - width * scale) / 2
  const offsetY = (newHeight - height * scale) / 2

  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(img, offsetX, offsetY, width * scale, height * scale)

  lastBuffer = buffer
}

function drawPlaceholder (text) {
  const canvas = canvasRef.value
  const container = containerRef.value
  if (!canvas || !container) return

  const ctx = canvas.getContext('2d')
  const rect = container.getBoundingClientRect()

  const dpr = window.devicePixelRatio || 1
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  canvas.style.width = `${rect.width}px`
  canvas.style.height = `${rect.height}px`

  ctx.setTransform(1, 0, 0, 1, 0, 0)
  ctx.scale(dpr, dpr)

  ctx.fillStyle = '#212121'
  ctx.fillRect(0, 0, rect.width, rect.height)

  ctx.fillStyle = '#aaa'
  ctx.font = '20px sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, rect.width / 2, rect.height / 2)
}



onMounted(() => {
  wsService.onBinary(data => {
    renderToCanvas(data)
  })

  const container = containerRef.value
  if (!container) return

  resizeObserver = new ResizeObserver(() => {
    if (lastBuffer) {
      renderToCanvas(lastBuffer)
    } else {
      drawPlaceholder('等待服务器响应.....')
    }
  })
  resizeObserver.observe(container)
})

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (currentImgUrl) {
    URL.revokeObjectURL(currentImgUrl)
    currentImgUrl = null
  }
})
</script>

<style scoped>
.websocket_view {
  width: 100%;
  height: 100%;
  overflow: hidden;
  position: relative;
  background: rgb(33, 33, 33);
}

.websocket_view-canvas {
  display: block;
  margin: 0 auto;
  width: 100%;
  height: 100%;
}
</style>
