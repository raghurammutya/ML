import axios from 'axios'
import type { ReplayWindowRequest, ReplayWindowResponse } from '../types/replay'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8081'

export async function fetchReplayWindow(params: ReplayWindowRequest): Promise<ReplayWindowResponse> {
  const response = await axios.get(`${API_BASE_URL}/replay/window`, {
    params: {
      underlying: params.underlying,
      timeframe: params.timeframe,
      start: params.start,
      end: params.end,
      expiries: params.expiries.join(','),
      strikes: params.strikes?.join(','),
      panels: params.panels.join(',')
    }
  })
  return response.data
}

export class ReplayWebSocketClient {
  private ws: WebSocket | null = null
  private messageHandler: ((data: any) => void) | null = null
  private reconnectTimeout: number | null = null

  constructor(private url: string) {}

  connect(onMessage: (data: any) => void) {
    this.messageHandler = onMessage
    this.ws = new WebSocket(this.url)

    this.ws.onopen = () => {
      console.log('[Replay WS] Connected')
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this.messageHandler?.(data)
      } catch (err) {
        console.error('[Replay WS] Parse error:', err)
      }
    }

    this.ws.onerror = (error) => {
      console.error('[Replay WS] Error:', error)
    }

    this.ws.onclose = () => {
      console.log('[Replay WS] Disconnected')
      // Auto-reconnect after 3s
      this.reconnectTimeout = window.setTimeout(() => {
        this.connect(onMessage)
      }, 3000)
    }
  }

  send(message: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    }
  }

  enterReplay(pageId: string, underlying: string, timeframe: string, cursor: string, windowSize: number) {
    this.send({
      action: 'enter_replay',
      pageId,
      underlying,
      timeframe,
      cursor,
      windowSize
    })
  }

  exitReplay(pageId: string) {
    this.send({
      action: 'exit_replay',
      pageId
    })
  }

  disconnect() {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
    }
    this.ws?.close()
    this.ws = null
  }
}
