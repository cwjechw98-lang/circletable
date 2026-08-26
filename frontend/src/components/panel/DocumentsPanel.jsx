import React from 'react'

const DOC_SIZE_ALLOWED = 10 * 1024 * 1024 // 10 MB

export default function DocumentsPanel({ roomId }) {
  const [files, setFiles] = React.useState([])
  const [knowledge, setKnowledge] = React.useState(null)
  const [uploading, setUploading] = React.useState(false)
  const [error, setError] = React.useState('')
  const [open, setOpen] = React.useState(true)
  const inputRef = React.useRef(null)

  React.useEffect(() => {
    if (!roomId) return
    fetch(`/api/rooms/${roomId}/documents`)
      .then((response) => (response.ok ? response.json() : { files: [] }))
      .then((data) => {
        setFiles(data.files || [])
        if (data.knowledge) setKnowledge(data.knowledge)
      })
      .catch(() => {})
  }, [roomId])

  React.useEffect(() => {
    if (!roomId) return undefined
    let cancelled = false

    async function refreshStatus() {
      try {
        const response = await fetch(`/api/rooms/${roomId}/knowledge/status`)
        if (!response.ok) return
        const data = await response.json()
        if (!cancelled) setKnowledge(data)
      } catch {
        // Status is supplementary; upload/list errors are shown separately.
      }
    }

    refreshStatus()
    const timer = window.setInterval(() => {
      if (knowledge?.status === 'building') {
        refreshStatus()
      }
    }, 1500)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [roomId, knowledge?.status])

  async function handleUpload(event) {
    const file = event.target.files?.[0]
    if (!file || !roomId) return
    if (file.size > DOC_SIZE_ALLOWED) {
      setError('Файл слишком большой (макс. 10 МБ).')
      return
    }
    setUploading(true)
    setError('')
    try {
      const form = new FormData()
      form.append('file', file)
      const response = await fetch(`/api/rooms/${roomId}/documents`, { method: 'POST', body: form })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Ошибка загрузки')
      setFiles(data.files || [])
      if (data.knowledge) setKnowledge(data.knowledge)
    } catch (err) {
      setError(err.message || 'Ошибка загрузки')
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  async function handleDelete(filename) {
    if (!roomId) return
    try {
      const response = await fetch(`/api/rooms/${roomId}/documents/${encodeURIComponent(filename)}`, { method: 'DELETE' })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Ошибка удаления')
      setFiles(data.files || [])
      if (data.knowledge) setKnowledge(data.knowledge)
    } catch (err) {
      setError(err.message || 'Ошибка удаления')
    }
  }

  if (!roomId) return null

  const knowledgeStatus = knowledge?.status || (files.length > 0 ? 'idle' : 'empty')
  const statusText = knowledgeStatus === 'building'
    ? `Индексируем: ${knowledge?.progress || 0}%`
    : knowledgeStatus === 'ready'
      ? `Граф готов: ${knowledge?.nodeCount || 0}/${knowledge?.edgeCount || 0}`
      : knowledgeStatus === 'error'
        ? 'Ошибка графа'
        : files.length > 0
          ? `${files.length} файл(ов)`
          : 'нет файлов'

  return (
    <div className={`documents-panel ${open ? 'is-open' : 'is-collapsed'}`}>
      <button
        type="button"
        className="documents-panel-toggle"
        onClick={() => setOpen((value) => !value)}
        data-hint="Открыть загрузку документов комнаты. PDF, Markdown и TXT индексируются в граф знаний, которым агенты пользуются автоматически через память комнаты."
      >
        <span>{open ? '▾' : '▸'} Документы комнаты</span>
        <span className={`documents-status-chip is-${knowledgeStatus}`}>{statusText}</span>
      </button>

      {open && (
        <>
          <div className="documents-panel-head">
            <div className="preset-panel-sub">
              Загрузите PDF, Markdown или TXT до старта или на паузе. После загрузки граф знаний перестраивается автоматически.
            </div>
          </div>
          {knowledge && (
            <div className={`documents-status is-${knowledge.status || 'idle'}`}>
              {knowledge.status === 'building'
                ? `Индексируем документы: ${knowledge.progress || 0}%`
                : knowledge.status === 'ready'
                  ? `Граф готов: ${knowledge.nodeCount || 0} узлов, ${knowledge.edgeCount || 0} связей`
                  : knowledge.status === 'error'
                    ? `Ошибка графа: ${knowledge.error || 'не удалось построить'}`
                    : files.length > 0
                      ? 'Файлы загружены. Граф построится после индексации.'
                      : 'Граф знаний ещё не создан.'}
            </div>
          )}
          <div className="documents-upload-row">
            <label
              className="pixel-btn ghost documents-upload-btn"
              data-hint="Загрузить документ PDF, Markdown или TXT. Можно делать до сессии или на паузе; новые факты попадут в следующие ответы."
            >
              {uploading ? 'Загрузка...' : '+ Загрузить файл'}
              <input
                ref={inputRef}
                type="file"
                accept=".txt,.md,.markdown,.pdf"
                style={{ display: 'none' }}
                onChange={handleUpload}
                disabled={uploading}
              />
            </label>
            {error && <span className="documents-error">{error}</span>}
          </div>
          {files.length > 0 && (
            <div className="documents-file-list">
              {files.map((file) => (
                <div key={file.name} className="documents-file-row">
                  <span className="documents-file-name" title={file.name}>{file.name}</span>
                  <span className="documents-file-size">{(file.size / 1024).toFixed(0)} кб</span>
                  <button
                    className="pixel-btn danger documents-delete-btn"
                    onClick={() => handleDelete(file.name)}
                    data-hint="Удалить этот документ из комнаты."
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
          {files.length === 0 && (
            <div className="preset-empty">Документов нет. Загрузите файл, чтобы агенты могли обращаться к нему.</div>
          )}
        </>
      )}
    </div>
  )
}
