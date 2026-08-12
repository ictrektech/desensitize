import { useState } from 'react'
import { api, Rule } from '../api/client'

interface Props {
  rules: Rule[]
  onRefresh: () => void
}

export default function RulesPage({ rules, onRefresh }: Props) {
  const [showModal, setShowModal] = useState(false)
  const [editingRule, setEditingRule] = useState<Rule | null>(null)
  const [form, setForm] = useState({
    name: '',
    description: '',
    pattern: '',
    placeholder: '[REDACTED]',
    priority: 0,
    enabled: true,
    category: 'custom',
  })
  const [error, setError] = useState('')
  const [testText, setTestText] = useState('')
  const [testResult, setTestResult] = useState<{ matched: boolean; result: string; match_count: number } | null>(null)
  const [testing, setTesting] = useState(false)

  const openCreate = () => {
    setEditingRule(null)
    setForm({ name: '', description: '', pattern: '', placeholder: '[REDACTED]', priority: 0, enabled: true, category: 'custom' })
    setError('')
    setTestText('')
    setTestResult(null)
    setShowModal(true)
  }

  const openEdit = (rule: Rule) => {
    if (rule.builtin) return
    setEditingRule(rule)
    setForm({
      name: rule.name,
      description: rule.description,
      pattern: rule.pattern,
      placeholder: rule.placeholder,
      priority: rule.priority,
      enabled: rule.enabled,
      category: rule.category,
    })
    setError('')
    setTestText('')
    setTestResult(null)
    setShowModal(true)
  }

  const handleTest = async () => {
    setError('')
    if (!form.pattern) {
      setError('请先填写正则表达式')
      return
    }
    if (!testText) {
      setError('请输入测试文本')
      return
    }
    setTesting(true)
    try {
      const result = await api.testPattern(form.pattern, testText, form.placeholder)
      setTestResult(result)
    } catch (e: any) {
      setError(e.message || '测试失败')
      setTestResult(null)
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    setError('')
    if (!form.name || !form.pattern) {
      setError('名称和正则表达式为必填项')
      return
    }
    try {
      if (editingRule) {
        await api.updateRule(editingRule.id, form)
      } else {
        await api.createRule(form)
      }
      setShowModal(false)
      onRefresh()
    } catch (e: any) {
      setError(e.message || '保存失败')
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确定删除这条自定义规则？')) return
    try {
      await api.deleteRule(id)
      onRefresh()
    } catch (e: any) {
      alert(e.message || '删除失败')
    }
  }

  const handleToggle = async (rule: Rule) => {
    try {
      await api.updateRule(rule.id, { enabled: !rule.enabled })
      onRefresh()
    } catch (e: any) {
      alert(e.message || '更新失败')
    }
  }

  const categoryBadge = (cat: string) => {
    const map: Record<string, string> = {
      pii: 'badge-pii',
      'api_key': 'badge-api-key',
      custom: 'badge-custom',
    }
    return <span className={`badge ${map[cat] || 'badge-custom'}`}>{cat}</span>
  }

  const builtinRules = rules.filter(r => r.builtin)
  const customRules = rules.filter(r => !r.builtin)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h2 style={{ fontSize: '18px' }}>规则列表</h2>
        <button className="btn btn-primary" onClick={openCreate}>+ 添加规则</button>
      </div>

      {/* 内置规则 */}
      <div className="card" style={{ padding: '12px 16px', marginBottom: '16px' }}>
        <div className="card-title" style={{ marginBottom: '8px' }}>
          内置规则 ({builtinRules.length})
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 'normal', marginLeft: '8px' }}>
            可启用/停用，不可修改、不可删除
          </span>
        </div>
      </div>
      {builtinRules.map(rule => (
        <div key={rule.id} className="rule-item">
          <div className="rule-header">
            <span className="rule-name">{rule.name}</span>
            <span className="badge badge-builtin">内置</span>
            {categoryBadge(rule.category)}
            <span className={`badge ${rule.enabled ? 'badge-enabled' : 'badge-disabled'}`}>
              {rule.enabled ? '已启用' : '已停用'}
            </span>
            <button
              className={`rule-toggle ${rule.enabled ? 'active' : ''}`}
              onClick={() => handleToggle(rule)}
              aria-pressed={rule.enabled}
              title={rule.enabled ? '停用此规则' : '启用此规则'}
            >
              <span className="rule-toggle-dot" />
              {rule.enabled ? '停用' : '启用'}
            </button>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>优先级: {rule.priority}</span>
          </div>
          {rule.description && <div className="rule-description">{rule.description}</div>}
          <div>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>正则: </span>
            <span className="rule-pattern">{rule.pattern}</span>
          </div>
          <div>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>替换为: </span>
            <span className="rule-placeholder">{rule.placeholder}</span>
          </div>
        </div>
      ))}

      {/* 自定义规则 */}
      <div className="card" style={{ padding: '12px 16px', marginBottom: '16px', marginTop: '24px' }}>
        <div className="card-title" style={{ marginBottom: '8px' }}>
          自定义规则 ({customRules.length})
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 'normal', marginLeft: '8px' }}>
            可添加、修改、删除、启用/停用
          </span>
        </div>
      </div>
      {customRules.length === 0 ? (
        <div className="empty-state" style={{ padding: '20px' }}>
          暂无自定义规则，点击右上角"添加规则"创建
        </div>
      ) : (
        customRules.map(rule => (
          <div key={rule.id} className="rule-item">
            <div className="rule-header">
              <span className="rule-name">{rule.name}</span>
              <span className="badge badge-custom">自定义</span>
              {categoryBadge(rule.category)}
              <span className={`badge ${rule.enabled ? 'badge-enabled' : 'badge-disabled'}`}>
                {rule.enabled ? '已启用' : '已停用'}
              </span>
              <button
                className={`rule-toggle ${rule.enabled ? 'active' : ''}`}
                onClick={() => handleToggle(rule)}
                aria-pressed={rule.enabled}
                title={rule.enabled ? '停用此规则' : '启用此规则'}
              >
                <span className="rule-toggle-dot" />
                {rule.enabled ? '停用' : '启用'}
              </button>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>优先级: {rule.priority}</span>
              <div className="rule-actions">
                <button className="btn btn-sm" onClick={() => openEdit(rule)}>编辑</button>
                <button className="btn btn-sm btn-danger" onClick={() => handleDelete(rule.id)}>删除</button>
              </div>
            </div>
            {rule.description && <div className="rule-description">{rule.description}</div>}
            <div>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>正则: </span>
              <span className="rule-pattern">{rule.pattern}</span>
            </div>
            <div>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>替换为: </span>
              <span className="rule-placeholder">{rule.placeholder}</span>
            </div>
          </div>
        ))
      )}

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-title">{editingRule ? '编辑规则' : '添加自定义规则'}</div>

            {error && <div className="result-box error">{error}</div>}

            <div className="form-group">
              <label className="form-label">规则名称 *</label>
              <input
                className="form-input"
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="例如: 企业微信Token"
              />
            </div>

            <div className="form-group">
              <label className="form-label">描述</label>
              <input
                className="form-input"
                value={form.description}
                onChange={e => setForm({ ...form, description: e.target.value })}
                placeholder="规则用途说明"
              />
            </div>

            <div className="form-group">
              <label className="form-label">正则表达式 *</label>
              <textarea
                className="form-textarea"
                value={form.pattern}
                onChange={e => setForm({ ...form, pattern: e.target.value })}
                placeholder="例如: \b(wwapi_[A-Za-z0-9]{20,})\b"
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">替换占位符</label>
                <input
                  className="form-input"
                  value={form.placeholder}
                  onChange={e => setForm({ ...form, placeholder: e.target.value })}
                  placeholder="[REDACTED]"
                />
              </div>
              <div className="form-group">
                <label className="form-label">优先级 (0-100)</label>
                <input
                  className="form-input"
                  type="number"
                  min="0"
                  max="100"
                  value={form.priority}
                  onChange={e => setForm({ ...form, priority: parseInt(e.target.value) || 0 })}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">分类</label>
              <select
                className="form-select"
                value={form.category}
                onChange={e => setForm({ ...form, category: e.target.value })}
              >
                <option value="custom">自定义</option>
                <option value="pii">PII (个人信息)</option>
                <option value="api_key">API Key (凭证)</option>
              </select>
            </div>

            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', marginBottom: '16px' }}>
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={e => setForm({ ...form, enabled: e.target.checked })}
              />
              启用此规则
            </label>

            {/* 测试区域 */}
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: '16px', marginBottom: '8px' }}>
              <div className="form-group">
                <label className="form-label">测试文本（保存前验证规则是否生效）</label>
                <textarea
                  className="form-textarea"
                  value={testText}
                  onChange={e => setTestText(e.target.value)}
                  placeholder="输入一段包含敏感信息的文本，例如: 我的密钥是 wwapi_abc123def456ghi789jkl"
                  style={{ minHeight: '60px' }}
                />
              </div>
              <button className="btn" onClick={handleTest} disabled={testing || !form.pattern || !testText}>
                {testing ? '测试中...' : '测试规则'}
              </button>

              {testResult && (
                <div className="result-box" style={{ marginTop: '12px' }}>
                  <div style={{ marginBottom: '4px' }}>
                    <strong>匹配结果:</strong> {testResult.matched ? (
                      <span style={{ color: 'var(--success)' }}>✓ 命中 {testResult.match_count} 处</span>
                    ) : (
                      <span style={{ color: 'var(--danger)' }}>✗ 未命中</span>
                    )}
                  </div>
                  <div style={{ marginTop: '8px' }}>
                    <strong>脱敏后:</strong>
                    <div style={{
                      marginTop: '4px',
                      padding: '8px',
                      background: 'var(--code-bg)',
                      borderRadius: '4px',
                      fontFamily: "'SF Mono', monospace",
                      fontSize: '13px',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-all',
                    }}>
                      {testResult.result}
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="modal-actions">
              <button className="btn" onClick={() => setShowModal(false)}>取消</button>
              <button className="btn btn-primary" onClick={handleSave}>保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
