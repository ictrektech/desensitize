import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ManagedModelInfo } from '../api/client'

const MODEL_KEYS: Array<'ner' | 'ocr'> = ['ner', 'ocr']

function percent(model: ManagedModelInfo) {
  const value = Number(model.task?.progress)
  if (Number.isFinite(value)) return Math.max(0, Math.min(100, value * 100))
  return model.ready ? 100 : 0
}

function statusText(model: ManagedModelInfo) {
  const task = model.task
  if (task && !['READY', 'FAILED'].includes(task.phase)) {
    return `${task.phase} · ${percent(model).toFixed(1)}%`
  }
  if (model.ready) return '已就绪'
  if (model.status === 'failed') return '下载失败'
  if (model.status === 'pulling') return '下载中'
  if (model.status === 'missing') return '未下载'
  return model.status || '未知'
}

function sizeText(bytes?: number) {
  if (!bytes || bytes <= 0) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

export default function ModelsPage() {
  const [models, setModels] = useState<ManagedModelInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busyKey, setBusyKey] = useState<string | null>(null)

  const hasRunningTask = useMemo(
    () => models.some(model => model.task && !['READY', 'FAILED'].includes(model.task.phase)),
    [models],
  )

  const loadModels = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true)
      setError('')
    }
    try {
      const data = await api.listManagedModels()
      const ordered = MODEL_KEYS.map(key => data.find(model => model.key === key)).filter(Boolean) as ManagedModelInfo[]
      setModels(ordered)
    } catch (e: any) {
      setError(e.message || '加载模型状态失败')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadModels()
  }, [loadModels])

  useEffect(() => {
    if (!hasRunningTask) return
    const timer = window.setInterval(() => loadModels(true), 3000)
    return () => window.clearInterval(timer)
  }, [hasRunningTask, loadModels])

  const runAction = async (key: 'ner' | 'ocr', action: 'download' | 'check' | 'update') => {
    setBusyKey(`${key}:${action}`)
    setError('')
    setMessage('')
    try {
      if (action === 'download') {
        await api.downloadManagedModel(key)
        setMessage(`${key === 'ner' ? 'NER' : 'OCR'} 模型下载已触发`)
      } else if (action === 'check') {
        const resp = await api.checkManagedModelUpdate(key)
        const result = resp.result || {}
        setMessage(result.has_update ? `${resp.model.name} 有新版本` : `${resp.model.name} 已是最新版本`)
      } else {
        await api.updateManagedModel(key)
        setMessage(`${key === 'ner' ? 'NER' : 'OCR'} 模型更新已触发`)
      }
      await loadModels(true)
    } catch (e: any) {
      setError(e.message || '模型操作失败')
      await loadModels(true)
    } finally {
      setBusyKey(null)
    }
  }

  if (loading) return <div className="empty-state">加载模型状态...</div>

  return (
    <div>
      {message && <div className="card"><div className="result-box">{message}</div></div>}
      {error && <div className="card"><div className="result-box error">{error}</div></div>}

      <div className="card">
        <div className="card-title">模型管理</div>
        <p className="model-help">
          NER 与 OCR 模型由 Model Hub 管理。这里的按钮只触发 Model Hub 下载、版本检查和更新；模型未就绪不影响文本纯规则脱敏。
        </p>
        <div className="model-grid">
          {models.map(model => {
            const running = Boolean(model.task && !['READY', 'FAILED'].includes(model.task.phase))
            const cardClass = running ? 'running' : model.ready ? 'ready' : 'pending'
            const canUpdate = model.ready && !running
            return (
              <div className={`model-card ${cardClass}`} key={model.key}>
                <div className="model-card-header">
                  <div>
                    <h3>{model.name}</h3>
                    <p>{model.description}</p>
                  </div>
                  <span className={`model-status ${cardClass}`}>{statusText(model)}</span>
                </div>

                <div className="model-meta">
                  <div><span>模型 ID</span><code>{model.model_id}</code></div>
                  <div><span>加载路径</span><code>{model.model_dir}</code></div>
                  <div><span>当前版本</span><code>{model.model?.version || '-'}</code></div>
                  <div><span>大小</span><code>{sizeText(Number(model.model?.size || 0))}</code></div>
                  <div><span>运行状态</span><code>{model.runtime?.state || '-'}</code></div>
                  <div><span>任务</span><code>{model.task ? `${model.task.phase} / ${model.task.task_id}` : '-'}</code></div>
                </div>

                <progress className="model-progress" max="100" value={percent(model)} />
                {model.task?.error_msg && <div className="result-box error">{model.task.error_msg}</div>}
                {model.runtime?.error && <div className="result-box error">{String(model.runtime.error)}</div>}

                <div className="model-actions">
                  <button
                    className="btn btn-primary"
                    disabled={model.ready || running || busyKey !== null}
                    onClick={() => runAction(model.key, 'download')}
                  >
                    {running ? '下载中' : model.ready ? '已下载' : '下载模型'}
                  </button>
                  <button
                    className="btn"
                    disabled={running || busyKey !== null}
                    onClick={() => runAction(model.key, 'check')}
                  >
                    检查版本
                  </button>
                  <button
                    className="btn"
                    disabled={!canUpdate || busyKey !== null}
                    onClick={() => runAction(model.key, 'update')}
                  >
                    更新模型
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
