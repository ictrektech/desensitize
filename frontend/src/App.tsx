import { useState, useEffect, useCallback } from 'react'
import { api, AboutInfo, Rule } from './api/client'
import RulesPage from './pages/RulesPage'
import IntegrationPage from './pages/IntegrationPage'
import TestPage from './pages/TestPage'
import ModelsPage from './pages/ModelsPage'

type Tab = 'rules' | 'test' | 'models' | 'integration'

export default function App() {
  const [tab, setTab] = useState<Tab>('rules')
  const [rules, setRules] = useState<Rule[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [aboutOpen, setAboutOpen] = useState(false)
  const [about, setAbout] = useState<AboutInfo | null>(null)
  const [aboutError, setAboutError] = useState('')

  const appVersion = window.__APP_VERSION__ || 'unknown'
  const frontendImage = window.__FRONTEND_IMAGE__ || ''

  const loadRules = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.listRules()
      setRules(data)
    } catch (e: any) {
      setError(e.message || '加载规则失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadRules()
  }, [loadRules])

  useEffect(() => {
    let cancelled = false

    const refreshWhenFrontendIsStale = async () => {
      if (!appVersion || appVersion === 'unknown') return
      try {
        const info = await api.about()
        if (cancelled || !info.app_version || info.app_version === appVersion) return

        const reloadKey = `desensitize-reloaded-${info.app_version}`
        if (sessionStorage.getItem(reloadKey) === '1') return
        sessionStorage.setItem(reloadKey, '1')
        window.location.reload()
      } catch {
        // Keep the app usable when the backend is still starting.
      }
    }

    refreshWhenFrontendIsStale()
    return () => {
      cancelled = true
    }
  }, [appVersion])

  const openAbout = async () => {
    setAboutOpen(true)
    setAboutError('')
    try {
      setAbout(await api.about())
    } catch (e: any) {
      setAboutError(e.message || '加载运行信息失败')
    }
  }

  const builtinCount = rules.filter(r => r.builtin).length
  const customCount = rules.filter(r => !r.builtin).length
  const enabledCount = rules.filter(r => r.enabled).length

  return (
    <div className="app">
      <div className="app-header">
        <div>
          <h1>数据脱敏服务</h1>
          <p>基于正则规则的敏感信息识别与脱敏，供 WeKnora、agent-room 等应用在调用云模型前统一脱敏</p>
        </div>
        <button className="btn about-button" onClick={openAbout}>关于</button>
      </div>

      <div className="stats">
        <div className="stat-item">
          <div className="stat-value">{rules.length}</div>
          <div className="stat-label">总规则数</div>
        </div>
        <div className="stat-item">
          <div className="stat-value">{builtinCount}</div>
          <div className="stat-label">内置规则</div>
        </div>
        <div className="stat-item">
          <div className="stat-value">{customCount}</div>
          <div className="stat-label">自定义规则</div>
        </div>
        <div className="stat-item">
          <div className="stat-value">{enabledCount}</div>
          <div className="stat-label">已启用</div>
        </div>
      </div>

      <div className="tabs">
        <button className={`tab ${tab === 'rules' ? 'active' : ''}`} onClick={() => setTab('rules')}>
          规则管理
        </button>
        <button className={`tab ${tab === 'test' ? 'active' : ''}`} onClick={() => setTab('test')}>
          脱敏测试
        </button>
        <button className={`tab ${tab === 'models' ? 'active' : ''}`} onClick={() => setTab('models')}>
          模型管理
        </button>
        <button className={`tab ${tab === 'integration' ? 'active' : ''}`} onClick={() => setTab('integration')}>
          接入指南
        </button>
      </div>

      {error && <div className="card"><div className="result-box error">{error}</div></div>}

      {loading ? (
        <div className="empty-state">加载中...</div>
      ) : (
        <>
          {tab === 'rules' && <RulesPage rules={rules} onRefresh={loadRules} />}
          {tab === 'test' && <TestPage rules={rules} />}
          {tab === 'models' && <ModelsPage />}
          {tab === 'integration' && <IntegrationPage />}
        </>
      )}

      {aboutOpen && (
        <div className="modal-overlay" onClick={() => setAboutOpen(false)}>
          <div className="modal about-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-title">关于数据脱敏服务</div>
            {aboutError && <div className="result-box error">{aboutError}</div>}
            <table>
              <tbody>
                <tr><th>服务 ID</th><td>{about?.service_id || 'com.ictrek.desensitize'}</td></tr>
                <tr><th>VOS App 版本</th><td>{about?.app_version || appVersion}</td></tr>
                <tr><th>当前 Profile</th><td>{about?.profile || '-'}</td></tr>
                <tr><th>前端镜像</th><td className="mono-cell">{frontendImage || about?.frontend_image || '-'}</td></tr>
                <tr><th>后端镜像</th><td className="mono-cell">{about?.backend_image || '-'}</td></tr>
                <tr><th>NER 状态</th><td>{about?.ner ? `${about.ner.state}${about.ner.enabled ? '' : ' / disabled'}` : '-'}</td></tr>
                <tr><th>NER Provider</th><td>{about?.ner?.active_provider || about?.ner?.requested_provider || '-'}</td></tr>
                <tr><th>NER 并发</th><td>{about?.ner ? `${about.ner.max_concurrency}，排队 ${about.ner.queue_timeout_seconds}s` : '-'}</td></tr>
                <tr><th>NER 模型</th><td className="mono-cell">{about?.ner?.model_id || '-'}</td></tr>
                <tr><th>图片 OCR</th><td>{about?.image_ocr ? `${about.image_ocr.state} / ${about.image_ocr.enabled ? 'enabled' : 'disabled'} / ${about.image_ocr.provider}` : '-'}</td></tr>
                <tr><th>OCR 并发</th><td>{about?.image_ocr ? `${about.image_ocr.max_concurrency}，排队 ${about.image_ocr.queue_timeout_seconds}s` : '-'}</td></tr>
                <tr><th>OCR 模型</th><td className="mono-cell">{about?.image_ocr?.model_id || '-'}</td></tr>
              </tbody>
            </table>
            {about?.ner?.error && <div className="result-box error">{about.ner.error}</div>}
            {about?.image_ocr?.error && <div className="result-box error">{about.image_ocr.error}</div>}
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={() => setAboutOpen(false)}>关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
