import { useState, useEffect, useCallback } from 'react'
import { api, Rule } from './api/client'
import RulesPage from './pages/RulesPage'
import IntegrationPage from './pages/IntegrationPage'
import TestPage from './pages/TestPage'

type Tab = 'rules' | 'test' | 'integration'

export default function App() {
  const [tab, setTab] = useState<Tab>('rules')
  const [rules, setRules] = useState<Rule[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

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

  const builtinCount = rules.filter(r => r.builtin).length
  const customCount = rules.filter(r => !r.builtin).length
  const enabledCount = rules.filter(r => r.enabled).length

  return (
    <div className="app">
      <div className="app-header">
        <h1>数据脱敏服务</h1>
        <p>基于正则规则的敏感信息识别与脱敏，供 WeKnora、agent-room 等应用在调用云模型前统一脱敏</p>
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
          {tab === 'integration' && <IntegrationPage />}
        </>
      )}
    </div>
  )
}
