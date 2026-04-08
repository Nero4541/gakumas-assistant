function withProbeParam (url) {
  const probeUrl = new URL(url, window.location.origin)
  probeUrl.searchParams.set('_probe', `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`)
  return probeUrl.toString()
}

export async function probeImage (url) {
  const response = await fetch(withProbeParam(url), { cache: 'no-store' })

  if (response.body) {
    void response.body.cancel().catch(() => {})
  }

  return response.ok
}
