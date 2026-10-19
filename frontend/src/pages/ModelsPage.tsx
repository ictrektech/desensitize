import { useI18n } from '../i18n'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ManagedModelInfo } from '../api/client'

const MODEL_KEYS: Array<'ner' | 'ocr'> = ['ner', 'ocr']

function percent(model: ManagedModelInfo) {
  const value = Number(model.task?.progress)
  if (Number.isFinite(value)) return Math.max(0, Math.min(100, value * 100))
  return model.ready ? 100 : 0
}

function statusText(model: ManagedModelInfo, t: (key: string) => string) {
  const task = model.task
  if (task && !['READY', 'FAILED'].includes(task.phase)) {
    return `${task.phase} · ${percent(model).toFixed(1)}%`
  }
  if (model.ready) return t("已就绪")
  if (model.status === 'failed') return t("下载失败")
  if (model.status === 'pulling') return t("下载中")
  if (model.status === 'missing') return t("未下载")
  return model.status || t("未知")
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
  const { t } = useI18n()
  const [models, setModels] = useState<ManagedModelInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState<{ key: string; model: string } | null>(null)
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
      setError(e.message || "加载模型状态失败")
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
    setMessage(null)
    try {
      if (action === 'download') {
        await api.downloadManagedModel(key)
        setMessage({ key: '{model} 模型下载已触发', model: key.toUpperCase() })
      } else if (action === 'check') {
        const resp = await api.checkManagedModelUpdate(key)
        const result = resp.result || {}
        setMessage({ key: result.has_update ? '{model} 有新版本' : '{model} 已是最新版本', model: resp.model.name })
      } else {
        await api.updateManagedModel(key)
        setMessage({ key: '{model} 模型更新已触发', model: key.toUpperCase() })
      }
      await loadModels(true)
    } catch (e: any) {
      setError(e.message || "模型操作失败")
      await loadModels(true)
    } finally {
      setBusyKey(null)
    }
  }

  if (loading) return <div className="empty-state">{t("加载模型状态...")}</div>

  return (
    <div>
      {message && <div className="card"><div className="result-box">{t(message.key, { model: t(message.model) })}</div></div>}
      {error && <div className="card"><div className="result-box error">{t(error)}</div></div>}

      <div className="card">
        <div className="card-title">{t("模型管理")}</div>
        <p className="model-help">{t("NER 与 OCR 模型由 V-Scheduler 管理。可在这里下载、检查版本和更新模型；推理需在 V-Scheduler 中授权。模型未就绪不影响文本纯规则脱敏。")}</p>
        <div className="model-grid">
          {models.map(model => {
            const running = Boolean(model.task && !['READY', 'FAILED'].includes(model.task.phase))
            const cardClass = running ? 'running' : model.ready ? 'ready' : 'pending'
            const canUpdate = model.ready && !running
            return (
              <div className={`model-card ${cardClass}`} key={model.key}>
                <div className="model-card-header">
                  <div>
                    <h3>{t(model.name)}</h3>
                    <p>{t(model.description)}</p>
                  </div>
                  <span className={`model-status ${cardClass}`}>{statusText(model, t)}</span>
                </div>

                <div className="model-meta">
                  <div><span>{t("模型 ID")}</span><code>{model.model_id}</code></div>
                  <div><span>{t("加载路径")}</span><code>{model.model_dir}</code></div>
                  <div><span>{t("当前版本")}</span><code>{model.model?.version || '-'}</code></div>
                  <div><span>{t("大小")}</span><code>{sizeText(Number(model.model?.size || 0))}</code></div>
                  <div><span>{t("运行状态")}</span><code>{model.runtime?.state || '-'}</code></div>
                  <div><span>{t("任务")}</span><code>{model.task ? `${model.task.phase} / ${model.task.task_id}` : '-'}</code></div>
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
                    {running ? t("下载中") : model.ready ? t("已下载") : t("下载模型")}
                  </button>
                  <button
                    className="btn"
                    disabled={running || busyKey !== null}
                    onClick={() => runAction(model.key, 'check')}
                  >{t("检查版本")}</button>
                  <button
                    className="btn"
                    disabled={!canUpdate || busyKey !== null}
                    onClick={() => runAction(model.key, 'update')}
                  >{t("更新模型")}</button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
