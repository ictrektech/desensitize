export type Locale = 'zh-CN' | 'en'

type Bridge = {
  getState: () => Promise<{ locale?: unknown }> | { locale?: unknown }
  broadcast: {
    on: (event: string, listener: (data: { locale?: unknown }) => void) => unknown
    off?: (event: string, listener: (data: { locale?: unknown }) => void) => void
  }
}

declare global { interface Window { vos_platform?: Bridge } }

export function normalizeLocale(value: unknown): Locale | null {
  if (typeof value !== 'string' || !value.trim()) return null
  return /^zh(?:[-_]|$)/i.test(value) ? 'zh-CN' : 'en'
}

function isLocaleKey(key: string) {
  return key === 'preferences-locale'
    || /^(VIVIBIT-|vben-web-antd-).*-preferences-locale$/.test(key)
}

export function readVosLocale(): Locale | null {
  try {
    const keys = Object.keys(localStorage).filter(isLocaleKey).sort((a, b) => b.localeCompare(a, undefined, { numeric: true }))
    for (const key of keys) {
      const raw = localStorage.getItem(key)
      if (!raw) continue
      let value: unknown = raw
      try {
        const parsed = JSON.parse(raw)
        value = parsed?.value ?? parsed
      } catch { /* Older VOS versions store plain locale strings. */ }
      const locale = normalizeLocale(value)
      if (locale) return locale
    }
  } catch { /* Storage can be unavailable outside VOS. */ }
  return null
}

export function initialLocale(): Locale {
  return (window.parent !== window ? readVosLocale() : null)
    || normalizeLocale(navigator.languages?.[0] || navigator.language) || 'en'
}

export function listenForVosLocale(apply: (locale: Locale) => void): () => void {
  let stopped = false
  let connected = false
  let timer: number | undefined
  let revision = 0
  let dispose: (() => void) | undefined
  const receive = (value: unknown) => {
    const locale = normalizeLocale(value)
    if (!stopped && locale) apply(locale)
  }
  const onChange = (data: { locale?: unknown }) => { revision += 1; receive(data?.locale) }
  const connect = () => {
    if (stopped || connected) return
    const bridge = window.vos_platform
    if (!bridge?.getState || !bridge.broadcast?.on) return
    try {
      const result = bridge.broadcast.on('locale-change', onChange)
      dispose = typeof result === 'function' ? result as () => void : () => bridge.broadcast.off?.('locale-change', onChange)
      connected = true
      window.clearInterval(timer)
      const snapshotRevision = revision
      Promise.resolve().then(() => bridge.getState()).then(state => {
        if (snapshotRevision === revision) receive(state?.locale)
      }).catch(() => { /* Later locale events can still update the page. */ })
    } catch { /* Retry if the bridge is not ready yet. */ }
  }
  const fallback = () => {
    if (!connected && window.parent !== window) receive(readVosLocale())
    connect()
  }
  const storage = (event: StorageEvent) => { if (!event.key || isLocaleKey(event.key)) fallback() }
  const browserLanguage = () => {
    if (window.parent === window && !connected) receive(navigator.languages?.[0] || navigator.language)
  }
  connect()
  // VOS injects the bridge after the iframe load event.
  if (!connected) timer = window.setInterval(connect, 250)
  window.addEventListener('storage', storage)
  window.addEventListener('focus', fallback)
  window.addEventListener('languagechange', browserLanguage)
  return () => {
    stopped = true
    window.clearInterval(timer)
    dispose?.()
    window.removeEventListener('storage', storage)
    window.removeEventListener('focus', fallback)
    window.removeEventListener('languagechange', browserLanguage)
  }
}
