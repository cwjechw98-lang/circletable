import React, { useEffect, useState } from 'react'
import { PROVIDER_PRESETS, STATIC_PROVIDER_LABELS } from '../constants/providers.js'

function providerLabel(name) {
  if (STATIC_PROVIDER_LABELS[name]) return STATIC_PROVIDER_LABELS[name]
  if (name.startsWith('custom:')) {
    const id = name.slice('custom:'.length)
    return `${id} (кастомный)`
  }
  return name
}

export default function ProvidersDrawer({ open, onClose, providers, onRefreshProviders }) {
  const [customProviders, setCustomProviders] = useState([])
  const [presets, setPresets] = useState(PROVIDER_PRESETS)
  const [form, setForm] = useState({ name: '', baseUrl: '', apiKey: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [testingId, setTestingId] = useState(null)

  useEffect(() => {
    if (!open) return
    fetch('/api/custom-providers')
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error('Не удалось загрузить провайдеров'))))
      .then((data) => setCustomProviders(data.customProviders || []))
      .catch(() => {})
    fetch('/api/custom-providers/presets')
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (data?.presets?.length) setPresets(data.presets)
      })
      .catch(() => {})
  }, [open])

  function applyPreset(preset) {
    setForm({
      name: preset.label,
      baseUrl: preset.baseUrl,
      apiKey: '',
    })
    setNotice(`Пресет «${preset.label}» подставлен — добавьте свой API-ключ.`)
    setError('')
  }

  async function addProvider(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const response = await fetch('/api/custom-providers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || 'Не удалось добавить провайдера')
      const listResponse = await fetch('/api/custom-providers')
      if (listResponse.ok) {
        const listData = await listResponse.json()
        setCustomProviders(listData.customProviders || [])
      }
      setForm({ name: '', baseUrl: '', apiKey: '' })
      setNotice(`Провайдер «${data.customProvider.name}» добавлен и уже доступен в списках моделей.`)
      onRefreshProviders?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function removeProvider(providerId) {
    setBusy(true)
    setError('')
    try {
      const response = await fetch(`/api/custom-providers/${providerId}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('Не удалось удалить провайдера')
      setCustomProviders((current) => current.filter((item) => item.id !== providerId))
      setNotice('Провайдер удалён.')
      onRefreshProviders?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function testProvider(providerId) {
    setTestingId(providerId)
    setError('')
    setNotice('')
    try {
      const response = await fetch(`/api/custom-providers/${providerId}/test`, { method: 'POST' })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || 'Проверка не удалась')
      setNotice(
        data.ok
          ? `Соединение в порядке, моделей доступно: ${data.modelCount}. Примеры: ${(data.modelsSample || []).slice(0, 4).join(', ') || '—'}`
          : 'Endpoint отвечает, но список моделей пуст.',
      )
    } catch (err) {
      setError(err.message)
    } finally {
      setTestingId(null)
    }
  }

  if (!open) return null

  const providerEntries = Object.entries(providers || {})

  return (
    <div className="drawer-shell" onClick={onClose}>
      <aside className="drawer drawer-right drawer-lab" onClick={(event) => event.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <div className="drawer-kicker">Настройки</div>
            <div className="drawer-title">Провайдеры моделей</div>
          </div>
          <button className="drawer-close" onClick={onClose}>×</button>
        </div>

        <div className="drawer-content lab-content">
          {error && <div className="drawer-empty lab-error">{error}</div>}
          {notice && !error && <div className="drawer-empty lab-notice">{notice}</div>}

          <div className="dossier-section-title">Активные источники</div>
          <div className="providers-active-list">
            {providerEntries.length === 0 && <div className="dossier-empty">Список ещё не загружен.</div>}
            {providerEntries.map(([name, info]) => (
              <div key={name} className={`provider-row${info.available ? ' is-available' : ''}`}>
                <span className={`provider-led${info.available ? ' on' : ''}`} />
                <span className="provider-row-name">{providerLabel(name)}</span>
                <span className="provider-row-meta">
                  {info.available ? `доступен · моделей: ${(info.models || []).length}` : 'недоступен'}
                </span>
              </div>
            ))}
          </div>

          <div className="dossier-section-title">Пресеты</div>
          <div className="providers-preset-grid">
            {presets.map((preset) => (
              <button key={preset.id} className="provider-preset-card" onClick={() => applyPreset(preset)}>
                <span className="provider-preset-label">{preset.label}</span>
                <span className="provider-preset-hint">{preset.hint}</span>
              </button>
            ))}
          </div>

          <div className="dossier-section-title">Добавить провайдера</div>
          <form className="providers-form" onSubmit={addProvider}>
            <label className="providers-form-field">
              <span>Имя</span>
              <input
                className="mini-input"
                value={form.name}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="Например: Мой шлюз"
                required
              />
            </label>
            <label className="providers-form-field">
              <span>Base URL (OpenAI-совместимый)</span>
              <input
                className="mini-input"
                value={form.baseUrl}
                onChange={(event) => setForm((current) => ({ ...current, baseUrl: event.target.value }))}
                placeholder="https://api.example.com/v1"
                required
              />
            </label>
            <label className="providers-form-field">
              <span>API-ключ (необязательно для локальных)</span>
              <input
                className="mini-input"
                type="password"
                value={form.apiKey}
                onChange={(event) => setForm((current) => ({ ...current, apiKey: event.target.value }))}
                placeholder="sk-..."
                autoComplete="off"
              />
            </label>
            <button className="pixel-btn add" type="submit" disabled={busy}>
              {busy ? 'Сохраняем...' : 'Добавить'}
            </button>
          </form>
          <div className="assistant-brain-note">
            Ключ хранится только в локальной базе на этом компьютере и никогда не попадает в git. После добавления
            провайдер появляется во всех выпадающих списках моделей.
          </div>

          {(customProviders.length > 0) && (
            <>
              <div className="dossier-section-title">Мои кастомные провайдеры</div>
              <div className="providers-active-list">
                {customProviders.map((item) => (
                  <div key={item.id} className="provider-row is-available">
                    <span className="provider-led on" />
                    <span className="provider-row-name">{item.name}</span>
                    <span className="provider-row-meta">{item.baseUrl} · ключ {item.keyHint || '—'}</span>
                    <span className="provider-row-actions">
                      <button
                        className="pixel-btn ghost"
                        onClick={() => testProvider(item.id)}
                        disabled={testingId === item.id}
                      >
                        {testingId === item.id ? '...' : 'Тест'}
                      </button>
                      <button className="pixel-btn danger" onClick={() => removeProvider(item.id)} disabled={busy}>
                        Удалить
                      </button>
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </aside>
    </div>
  )
}
