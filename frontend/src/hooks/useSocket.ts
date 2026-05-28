/**
 * uriv-syncboard / frontend / src / hooks / useSocket.ts
 *
 * FIXES:
 *  1. dbSessionId is now extracted from session_update messages and stored in state.
 *  2. Ping/pong keepalive to prevent proxy timeouts.
 *  3. Auto-reconnect with exponential backoff.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { socket } from '../api/socket'
import type { ClientMsg, OcrLine, PageSnapshot, SessionInfo, StatusMsg } from '../types'

export interface SyncBoardState {
  connected:    boolean
  frameDataUrl: string | null
  ocrText:      string
  confidence:   number
  ocrLines:     OcrLine[]
  boardCleared: boolean
  session:      SessionInfo
  status:       StatusMsg | null
  // FIX: exposed so App can pass it to LiveNotes for export calls
  dbSessionId:  string | null
}

const DEFAULT_SESSION: SessionInfo = {
  name: 'New Session',
  page_count: 0,
  pages: [],
}

export function useSocket() {
  const [state, setState] = useState<SyncBoardState>({
    connected:    false,
    frameDataUrl: null,
    ocrText:      '',
    confidence:   0,
    ocrLines:     [],
    boardCleared: false,
    session:      DEFAULT_SESSION,
    status:       null,
    dbSessionId:  null,
  })

  const [lastCapturedSeq, setLastCapturedSeq] = useState<number | null>(null)
  const clearTimer    = useRef<ReturnType<typeof setTimeout>>()
  const statusTimer   = useRef<ReturnType<typeof setTimeout>>()
  const pingTimer     = useRef<ReturnType<typeof setInterval>>()

  useEffect(() => {
    socket.connect()

    // Keepalive ping every 25s to prevent proxy/nginx timeouts
    pingTimer.current = setInterval(() => {
      if (socket.isConnected) socket.send({ type: 'ping' } as any)
    }, 25_000)

    const remove = socket.onMessage((msg) => {
      switch (msg.type) {

        case 'frame':
          setState(s => ({
            ...s,
            connected:    true,
            frameDataUrl: `data:image/jpeg;base64,${msg.data}`,
          }))
          break

        case 'ocr_update':
          setState(s => ({
            ...s,
            ocrText:    msg.text,
            confidence: msg.confidence,
            ocrLines:   msg.lines,
          }))
          break

        case 'board_cleared':
          setState(s => ({ ...s, boardCleared: true }))
          clearTimeout(clearTimer.current)
          clearTimer.current = setTimeout(
            () => setState(s => ({ ...s, boardCleared: false })),
            2000,
          )
          break

        case 'page_captured':
          setLastCapturedSeq(msg.page.seq)
          break

        case 'session_update':
          // FIX: extract db_session_id that was added to the payload
          setState(s => ({
            ...s,
            session:     msg.session,
            dbSessionId: (msg.session as any).db_session_id ?? s.dbSessionId,
          }))
          break

        case 'status':
          setState(s => ({ ...s, status: { message: msg.message, level: msg.level } }))
          clearTimeout(statusTimer.current)
          statusTimer.current = setTimeout(
            () => setState(s => ({ ...s, status: null })),
            5000,
          )
          break

        case 'error':
          setState(s => ({
            ...s,
            status: { message: msg.message, level: 'error' },
          }))
          break
      }
    })

    // Heartbeat to reflect disconnect in UI
    const hb = setInterval(() => {
      setState(s => ({ ...s, connected: socket.isConnected }))
    }, 1500)

    return () => {
      remove()
      clearInterval(hb)
      clearInterval(pingTimer.current)
      clearTimeout(clearTimer.current)
      clearTimeout(statusTimer.current)
    }
  }, [])

  const send = useCallback((msg: ClientMsg) => socket.send(msg), [])

  return { state, send, lastCapturedSeq }
}
