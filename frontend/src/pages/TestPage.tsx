import { useState } from 'react'
import { api, Rule } from '../api/client'

interface Props {
  rules: Rule[]
}

export default function TestPage({ rules }: Props) {
  const [input, setInput] = useState('我的手机号是13812345678，身份证是110101199001011234，密钥 sk-live-abc123def456ghi789jkl012mno345pqr')
  const [output, setOutput] = useState('')
  const [replaced, setReplaced] = useState<{ rule: string; placeholder: string; occurrences: number }[]>([])
  const [latency, setLatency] = useState(0)
  const [error, setError] = useState('')
  const [useNer, setUseNer] = useState(false)

  const handleTest = async () => {
    setError('')
    try {
      const resp = await api.desensitizeText(input, undefined, useNer)
      setOutput(resp.text)
      setReplaced(resp.replaced)
      setLatency(resp.latency_ms)
    } catch (e: any) {
      setError(e.message || '脱敏失败')
      setOutput('')
      setReplaced([])
    }
  }

  const handleClear = () => {
    setInput('')
    setOutput('')
    setReplaced([])
    setError('')
    setLatency(0)
  }

  const categoryColor = (cat: string) => {
    const map: Record<string, string> = { pii: '#38a169', api_key: '#e53e3e', custom: '#d69e2e' }
    return map[cat] || '#718096'
  }

  return (
    <div>
      <div className="card">
        <div className="card-title">脱敏测试</div>
        <div className="form-group">
          <label className="form-label">输入文本</label>
          <textarea
            className="form-textarea"
            value={input}
            onChange={e => setInput(e.target.value)}
            style={{ minHeight: '120px' }}
            placeholder="输入要脱敏的文本..."
          />
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '12px', fontSize: '13px', color: 'var(--text-secondary)' }}>
          <input type="checkbox" checked={useNer} onChange={e => setUseNer(e.target.checked)} />
          启用 NER（需要已在 Model Hub 安装模型；识别人名和地址）
        </label>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-primary" onClick={handleTest}>执行脱敏</button>
          <button className="btn" onClick={handleClear}>清空</button>
        </div>
      </div>

      {error && (
        <div className="card">
          <div className="result-box error">{error}</div>
        </div>
      )}

      {output && (
        <>
          <div className="card">
            <div className="card-title">脱敏结果</div>
            <div style={{ display: 'flex', gap: '12px', marginBottom: '12px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                耗时: <strong style={{ color: 'var(--primary)' }}>{latency}ms</strong>
              </span>
              <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                命中规则: <strong style={{ color: 'var(--success)' }}>{replaced.length}</strong> 条
              </span>
            </div>
            <div style={{
              padding: '12px',
              background: 'var(--code-bg)',
              borderRadius: 'var(--radius)',
              fontSize: '14px',
              fontFamily: "'SF Mono', monospace",
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
              minHeight: '60px',
            }}>
              {output}
            </div>
          </div>

          {replaced.length > 0 && (
            <div className="card">
              <div className="card-title">命中详情</div>
              <table>
                <thead>
                  <tr>
                    <th>规则名称</th>
                    <th>替换为</th>
                    <th>命中次数</th>
                  </tr>
                </thead>
                <tbody>
                  {replaced.map((r, i) => (
                    <tr key={i}>
                      <td>{r.rule}</td>
                      <td><span className="rule-placeholder">{r.placeholder}</span></td>
                      <td>{r.occurrences}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <div className="card">
        <div className="card-title">当前可用规则</div>
        <table>
          <thead>
            <tr>
              <th>规则名称</th>
              <th>分类</th>
              <th>占位符</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {rules.map(r => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td style={{ color: categoryColor(r.category) }}>{r.category}</td>
                <td><span className="rule-placeholder">{r.placeholder}</span></td>
                <td>{r.enabled ? '✓' : '✗'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
