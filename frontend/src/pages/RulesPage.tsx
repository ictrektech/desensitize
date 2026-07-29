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

  const openCreate = () => {
    setEditingRule(null)
    setForm({ name: '', description: '', pattern: '', placeholder: '[REDACTED]', priority: 0, enabled: true, category: 'custom' })
    setError('')
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
    setShowModal(true)
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
    if (rule.builtin) return
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

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h2 style={{ fontSize: '18px' }}>规则列表</h2>
        <button className="btn btn-primary" onClick={openCreate}>+ 添加规则</button>
      </div>

      {rules.length === 0 ? (
        <div className="empty-state">暂无规则</div>
      ) : (
        rules.map(rule => (
          <div key={rule.id} className="rule-item">
            <div className="rule-header">
              <span className="rule-name">{rule.name}</span>
              <span className={`badge ${rule.builtin ? 'badge-builtin' : 'badge-custom'}`}>
                {rule.builtin ? '内置' : '自定义'}
              </span>
              {categoryBadge(rule.category)}
              <span className={`badge ${rule.enabled ? 'badge-enabled' : 'badge-disabled'}`}>
                {rule.enabled ? '启用' : '禁用'}
              </span>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>优先级: {rule.priority}</span>
              <div className="rule-actions">
                {!rule.builtin && (
                  <>
                    <button className="btn btn-sm" onClick={() => openEdit(rule)}>编辑</button>
                    <button className="btn btn-sm" onClick={() => handleToggle(rule)}>
                      {rule.enabled ? '禁用' : '启用'}
                    </button>
                    <button className="btn btn-sm btn-danger" onClick={() => handleDelete(rule.id)}>删除</button>
                  </>
                )}
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

            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px' }}>
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={e => setForm({ ...form, enabled: e.target.checked })}
              />
              启用此规则
            </label>

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
