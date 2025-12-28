export function getWsUrl(path = '/ws') {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${location.host}${path}`
}
