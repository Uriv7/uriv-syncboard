// ══════════════════════════════════════════════════════════════
//  SyncBoard — shared TypeScript types
// ══════════════════════════════════════════════════════════════

export interface OcrLine {
  text:       string
  confidence: number
}

export interface PageSnapshot {
  seq:        number
  text:       string
  confidence: number
  timestamp:  string
}

export interface SessionInfo {
  name:       string
  page_count: number
  pages:      PageSnapshot[]
}

export interface StatusMsg {
  message: string
  level:   'info' | 'success' | 'error'
}

// ── WebSocket message union ────────────────────────────────────

export type ServerMsg =
  | { type: 'frame';          data: string }
  | { type: 'ocr_update';     text: string; confidence: number; lines: OcrLine[] }
  | { type: 'page_captured';  page: PageSnapshot }
  | { type: 'board_cleared' }
  | { type: 'text_stable';    text: string }
  | { type: 'session_update'; session: SessionInfo }
  | { type: 'status';         message: string; level: StatusMsg['level'] }
  | { type: 'error';          message: string }

// ── Client → Server ───────────────────────────────────────────

export type ClientMsg =
  | { type: 'start_webcam';  device_index?: number }
  | { type: 'start_video';   path: string }
  | { type: 'start_images';  paths: string[] }
  | { type: 'stop' }
  | { type: 'set_roi';       x: number; y: number; w: number; h: number }
  | { type: 'clear_roi' }
  | { type: 'capture_page' }
  | { type: 'set_reference' }
  | { type: 'toggle_auto';   enabled: boolean }
  | { type: 'delete_page';   page_id: number }
  | { type: 'new_session' }

export type ExportFmt = 'pdf' | 'docx' | 'pptx' | 'markdown' | 'txt' | 'json'
