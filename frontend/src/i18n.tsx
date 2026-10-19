import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import messages from './messages.en.json'
import { initialLocale, listenForVosLocale, type Locale } from './locale'

const english: Record<string, string> = messages
const I18nContext = createContext<Locale>('zh-CN')

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState(initialLocale)
  useEffect(() => listenForVosLocale(setLocale), [])
  useEffect(() => {
    document.documentElement.lang = locale
    document.title = locale === 'en' ? 'Desensitize Service' : '数据脱敏服务'
  }, [locale])
  return <I18nContext.Provider value={locale}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const locale = useContext(I18nContext)
  const t = (text: string, params?: Record<string, string | number>) => {
    let result = locale === 'en' ? english[text] ?? text : text
    for (const [key, value] of Object.entries(params || {})) result = result.split(`{${key}}`).join(String(value))
    return result
  }
  return { locale, t }
}
