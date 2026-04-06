import { useRef, useEffect, useCallback } from 'react'

const DEV_FRONTEND_PORT = '43118'
const DEV_BACKEND_PORT = '43117'

function resolveBackendOrigin() {
  const explicitOrigin = import.meta.env.VITE_API_PROXY_TARGET
  if (explicitOrigin) {
    return explicitOrigin
  }

  const { protocol, hostname, port, origin } = window.location
  if (port === DEV_FRONTEND_PORT) {
    return `${protocol}//${hostname}:${DEV_BACKEND_PORT}`
  }

  return origin
}

const WS_URL = `${resolveBackendOrigin().replace(/^http/, 'ws')}/ws`

export function useWebSocket(onMessage) {
  const wsRef = useRef(null)
  const cbRef = useRef(onMessage)
  const timerRef = useRef(null)
  const reconnectEnabledRef = useRef(true)

  useEffect(() => { cbRef.current = onMessage }, [onMessage])

  const connect = useCallback(() => {
    if (!reconnectEnabledRef.current) return

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      if (ws !== wsRef.current || !reconnectEnabledRef.current) {
        ws.close()
        return
      }

      cbRef.current({ type: '_ws_open' })
    }

    ws.onmessage = (e) => {
      if (ws !== wsRef.current || !reconnectEnabledRef.current) return

      try { cbRef.current(JSON.parse(e.data)) }
      catch { /* skip malformed */ }
    }

    ws.onclose = () => {
      if (ws !== wsRef.current) return

      wsRef.current = null

      if (!reconnectEnabledRef.current) return

      cbRef.current({ type: '_ws_close' })
      timerRef.current = setTimeout(connect, 2000)
    }

    ws.onerror = () => ws.close()
  }, [])

  useEffect(() => {
    reconnectEnabledRef.current = true
    connect()

    return () => {
      reconnectEnabledRef.current = false
      clearTimeout(timerRef.current)
      const ws = wsRef.current
      wsRef.current = null

      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        ws.close()
      }
    }
  }, [connect])

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  return { send }
}
