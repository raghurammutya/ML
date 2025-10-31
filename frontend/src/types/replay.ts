export interface ReplayState {
  isActive: boolean
  cursorUtc: string | null
  timeframe: string
  playbackSpeed: number
  isPlaying: boolean
  isFollowingMain: boolean
  windowStartUtc: string | null
  windowEndUtc: string | null
  availableRange: {
    earliestUtc: string
    latestUtc: string
  } | null
  bufferedData: {
    timestamps: string[]
    candles: any[]
    panels: Record<string, any[]>
  } | null
}

export interface ReplayControls {
  enter: () => Promise<void>
  exit: () => void
  play: () => void
  pause: () => void
  stepForward: () => void
  stepBackward: () => void
  seek: (timestamp: string) => void
  setSpeed: (speed: number) => void
  rewind: () => void
  fastForward: () => void
}

export interface PerformanceMode {
  enabled: boolean
  reducedCadence: number
  disableSparklines: boolean
  reducedPointDensity: boolean
}

export interface ReplayWindowRequest {
  underlying: string
  timeframe: string
  start: string
  end: string
  expiries: string[]
  strikes?: number[]
  panels: string[]
}

export interface ReplayWindowResponse {
  status: string
  underlying: string
  timeframe: string
  range: {
    start: string
    end: string
  }
  timestamps: string[]
  priceSeries: {
    timestamps: string[]
    candles: Array<{o: number, h: number, l: number, c: number, v: number}>
  }
  panels: {
    [panelId: string]: {
      series: Array<{
        expiry: string
        bucket?: string
        strike?: number
        points: Array<{time: string, value: number}>
      }>
    }
  }
}

export interface ReplayFrameMessage {
  type: 'replay_frame'
  seq: number
  timestamp: string
  payload: {
    ltp: number
    candle: {o: number, h: number, l: number, c: number, v: number}
    panels: {
      [panelId: string]: {
        series: Array<{
          expiry: string
          strike?: number
          bucket?: string
          points: Array<{time: string, value: number}>
        }>
      }
    }
  }
}

export interface BackpressureMessage {
  type: 'backpressure'
  suggested_cadence: number
  reason: 'high_subscription_count' | 'server_load' | 'client_lag'
  message: string
}
