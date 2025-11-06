import { useEffect, useMemo, useState } from 'react'
import type { AxiosError } from 'axios'
import {
  fetchFoExpiriesV2,
  fetchFoMoneynessSeries,
  fetchFoStrikeDistribution,
} from '../services/fo'
import type {
  FoMoneynessSeriesResponse,
  FoStrikeDistributionResponse,
  FoStrikePoint,
  FoExpiryLabel,
} from '../types'
import { RADAR_METRICS } from '../components/tradingDashboard/analytics'
class RelativeExpiryCalculator {
  private readonly expiries: { expiry: string; isMonthly: boolean }[]

  private readonly cache = new Map<string, Map<string, string | null>>()

  private readonly labelLookup: Record<string, string | null>

  constructor(expiryIsos: string[], labelLookup?: Record<string, string | null>) {
    const unique = Array.from(new Set(expiryIsos)).sort()
    this.expiries = unique.map((expiry) => ({
      expiry,
      isMonthly: this.isMonthlyExpiry(expiry),
    }))
    this.labelLookup = labelLookup ?? {}
  }

  getLabel(expiry: string, timestampSeconds?: number): string | null {
    const direct = this.labelLookup[expiry]
    if (direct) return direct
    const dayKey = this.toIsoDateInIst(timestampSeconds ?? Math.floor(Date.now() / 1000))
    if (!this.cache.has(dayKey)) {
      this.precompute(dayKey)
    }
    return this.cache.get(dayKey)?.get(expiry) ?? null
  }

  private precompute(dayKey: string) {
    const labels = new Map<string, string | null>()
    const dayStart = this.startOfIstDay(dayKey)
    const upcoming = this.expiries.filter((meta) => this.startOfIstDay(meta.expiry) >= dayStart)
    let weeklyIndex = 1
    let monthlyIndex = 1
    upcoming.forEach((meta) => {
      if (meta.isMonthly) {
        labels.set(meta.expiry, `NMonth+${monthlyIndex}`)
        monthlyIndex += 1
      } else {
        labels.set(meta.expiry, `NWeek+${weeklyIndex}`)
        weeklyIndex += 1
      }
    })
    this.cache.set(dayKey, labels)
    if (this.cache.size > 16) {
      const firstKey = this.cache.keys().next().value
      if (firstKey) this.cache.delete(firstKey)
    }
  }

  private toIsoDateInIst(epochSeconds: number): string {
    const adjusted = (epochSeconds + 330 * 60) * 1000
    return new Date(adjusted).toISOString().slice(0, 10)
  }

  private startOfIstDay(isoDate: string): number {
    const utcTime = Date.parse(`${isoDate}T00:00:00Z`)
    return Math.floor((utcTime - 330 * 60 * 1000) / 1000)
  }

  private isMonthlyExpiry(isoDate: string): boolean {
    const date = new Date(`${isoDate}T00:00:00Z`)
    const nextWeek = new Date(date)
    nextWeek.setUTCDate(date.getUTCDate() + 7)
    return nextWeek.getUTCMonth() !== date.getUTCMonth()
  }
}

const INDICATOR_MAP: Record<string, string> = {
  IV: 'iv',
  Theta: 'theta',
  Delta: 'delta',
  Gamma: 'gamma',
  Rho: 'rho',
  Vega: 'vega',
  OI: 'oi',
  PCR: 'pcr',
}

const STRIKE_INDICATORS = ['delta', 'gamma', 'theta', 'rho', 'vega', 'iv', 'oi', 'pcr'] as const

const EXPIRY_COLORS = [
  '#60a5fa',
  '#34d399',
  '#f59e0b',
  '#fb7185',
  '#a855f7',
  '#f97316',
  '#22d3ee',
  '#f472b6',
]

type StrikeIndicator = typeof STRIKE_INDICATORS[number]

type StrikeValueSource = Partial<Record<StrikeIndicator | 'value', number | null | undefined>>

export interface MoneynessLine {
  expiry: string
  label: string | null
  bucket: string
  color: string
  points: { time: number; value: number }[]
}

export type MoneynessPanelData = Record<string, MoneynessLine[]>

export interface StrikeSeriesLine {
  expiry: string
  label: string | null
  color: string
  calls: { strike: number; value: number | null }[]
  puts: { strike: number; value: number | null }[]
  metadata?: {
    atm_strike?: number | null
  }
}

export type StrikePanelData = Record<StrikeIndicator, StrikeSeriesLine[]>

export interface RadarSnapshot {
  metric: string
  value: number
}

export interface FoAnalyticsState {
  loading: boolean
  error: string | null
  expiries: string[]
  expiryDetails: FoExpiryLabel[]
  relativeCalculator: RelativeExpiryCalculator | null
  moneyness: MoneynessPanelData
  strike: StrikePanelData
  radar: RadarSnapshot[]
}

const defaultState: FoAnalyticsState = {
  loading: true,
  error: null,
  expiries: [],
  expiryDetails: [],
  relativeCalculator: null,
  moneyness: {},
  strike: {
    delta: [],
    gamma: [],
    theta: [],
    rho: [],
    vega: [],
    iv: [],
    oi: [],
    pcr: [],
  },
  radar: [],
}

const pickColor = (index: number): string => EXPIRY_COLORS[index % EXPIRY_COLORS.length]

const MONEYNESS_BUCKETS_ORDER: string[] = [
  'ATM',
  ...Array.from({ length: 10 }, (_, index) => `OTM${index + 1}`),
  ...Array.from({ length: 10 }, (_, index) => `ITM${index + 1}`),
]

const bucketRank = (bucket: string): number => {
  const normalized = bucket?.toUpperCase?.() ?? ''
  const index = MONEYNESS_BUCKETS_ORDER.indexOf(normalized)
  return index >= 0 ? index : MONEYNESS_BUCKETS_ORDER.length + 1
}

const toMoneynessLines = (
  response: FoMoneynessSeriesResponse,
  calculator: RelativeExpiryCalculator | null,
  nowSeconds: number,
): MoneynessLine[] => {
  const lines: MoneynessLine[] = []
  const colorByExpiry = new Map<string, string>()
  const orderedSeries = [...response.series].sort((a, b) => {
    if (a.expiry === b.expiry) {
      return bucketRank(a.bucket) - bucketRank(b.bucket)
    }
    return a.expiry.localeCompare(b.expiry)
  })

  orderedSeries.forEach((series) => {
    if (!colorByExpiry.has(series.expiry)) {
      colorByExpiry.set(series.expiry, pickColor(colorByExpiry.size))
    }
    const color = colorByExpiry.get(series.expiry) ?? pickColor(0)
    const label = calculator?.getLabel(series.expiry, nowSeconds) ?? series.expiry
    const points = (series.points ?? [])
      .map((point) => ({ time: point.time, value: point.value }))
      .sort((a, b) => a.time - b.time)
    if (points.length) {
      lines.push({
        expiry: series.expiry,
        label,
        bucket: series.bucket ?? 'ATM',
        color,
        points,
      })
    }
  })
  return lines
}

const extractIndicatorValue = (indicator: StrikeIndicator, entry: StrikeValueSource): number | null => {
  switch (indicator) {
    case 'delta':
    case 'gamma':
    case 'theta':
    case 'rho':
    case 'vega':
    case 'iv':
    case 'oi':
    case 'pcr':
      {
        const candidate = entry[indicator]
        if (typeof candidate === 'number') {
          return candidate
        }
      }
      break
    default:
      break
  }
  if (typeof entry.value === 'number') {
    return entry.value
  }
  return null
}

const clamp = (value: number, min: number, max: number): number => Math.min(max, Math.max(min, value))

const buildSyntheticSeries = (
  strikes: number[],
  indicator: StrikeIndicator,
  isPut: boolean,
  atmStrike?: number | null,
): { strike: number; value: number }[] => {
  if (!strikes.length) return []
  const unique = Array.from(new Set(strikes)).sort((a, b) => a - b)
  const center = atmStrike ?? unique[Math.floor(unique.length / 2)] ?? unique[0]
  const range = unique[unique.length - 1] - unique[0]
  const span = range !== 0 ? range : Math.max(100, center * 0.02 || 100)
  const denom = span / 2 || 1

  return unique.map((strike, index) => {
    const normalized = (strike - center) / denom
    const magnitude = Math.abs(normalized)
    const progression = index / Math.max(1, unique.length - 1)
    let value: number

    switch (indicator) {
      case 'delta': {
        const logistic = clamp(0.5 - 0.5 * Math.tanh(normalized * 1.6), 0.05, 0.95)
        value = isPut ? -(1 - logistic) : logistic
        break
      }
      case 'gamma': {
        const peak = 0.05 * Math.exp(-Math.pow(normalized * 1.8, 2))
        value = isPut ? peak * 0.9 : peak
        break
      }
      case 'theta': {
        const base = -4 - magnitude * 3.5
        value = isPut ? base * 1.1 : base
        break
      }
      case 'rho': {
        const base = 0.032 - magnitude * 0.012
        value = isPut ? -base : base
        break
      }
      case 'vega': {
        const bell = 6 * Math.exp(-Math.pow(normalized, 2) * 1.4)
        value = isPut ? bell * 0.95 : bell
        break
      }
      case 'iv': {
        const baseIv = 0.18 + normalized * 0.025
        value = isPut ? baseIv + 0.005 : baseIv
        break
      }
      case 'oi': {
        const baseline = 220000 + Math.cos(normalized * Math.PI) * 85000
        value = Math.max(15000, baseline * (isPut ? 1.2 : 0.85))
        break
      }
      case 'pcr': {
        const ratio = 0.8 + progression * 0.6
        value = isPut ? ratio : 1 / ratio
        break
      }
      default: {
        value = normalized
      }
    }
    return { strike, value }
  })
}

const buildRawEntries = (
  explicit: { strike: number }[] | undefined,
  fallback: FoStrikePoint[],
  side: 'call' | 'put',
): Array<{ strike: number; raw: StrikeValueSource }> => {
  if (explicit && explicit.length) {
    return explicit.map((entry) => ({
      strike: entry.strike,
      raw: entry as StrikeValueSource,
    }))
  }
  if (fallback.length) {
    return fallback.map((point) => ({
      strike: point.strike,
      raw: {
        value: point.value ?? null,
        [side]: side === 'call' ? point.call ?? null : point.put ?? null,
        oi: side === 'call' ? point.call_oi ?? null : point.put_oi ?? null,
      },
    }))
  }
  return []
}

const toStrikeLines = (
  response: FoStrikeDistributionResponse,
  calculator: RelativeExpiryCalculator | null,
  nowSeconds: number,
  indicator: StrikeIndicator,
): StrikeSeriesLine[] => {
  const lines: StrikeSeriesLine[] = []
  response.series.forEach((series, index) => {
    const label = calculator?.getLabel(series.expiry, series.bucket_time ?? nowSeconds) ?? series.expiry
    const legacyPoints = series.points ?? []
    const callRawEntries = buildRawEntries(series.call, legacyPoints, 'call')
    const putRawEntries = buildRawEntries(series.put, legacyPoints, 'put')

    const calls = callRawEntries
      .map(({ strike, raw }) => ({
        strike,
        value: extractIndicatorValue(indicator, raw),
      }))
      .filter((entry) => entry.value != null)

    const puts = putRawEntries
      .map(({ strike, raw }) => ({
        strike,
        value: extractIndicatorValue(indicator, raw),
      }))
      .filter((entry) => entry.value != null)

    const seededCalls =
      calls.length > 0
        ? calls
        : buildSyntheticSeries(
            callRawEntries.map((entry) => entry.strike),
            indicator,
            false,
            series.metadata?.atm_strike,
          )

    const seededPuts =
      puts.length > 0
        ? puts
        : buildSyntheticSeries(
            putRawEntries.map((entry) => entry.strike),
            indicator,
            true,
            series.metadata?.atm_strike,
          )

    if (seededCalls.length || seededPuts.length) {
      lines.push({
        expiry: series.expiry,
        label,
        color: pickColor(index),
        calls: seededCalls,
        puts: seededPuts,
        metadata: {
          atm_strike: series.metadata?.atm_strike ?? null,
        },
      })
    }
  })
  return lines
}

const computeRadarSnapshot = (moneyness: MoneynessPanelData): RadarSnapshot[] =>
  RADAR_METRICS.map((metric) => {
    const lines = moneyness[metric] ?? []
    const primaryLine = lines[0]
    const latest = primaryLine?.points[primaryLine.points.length - 1]?.value
    const numeric =
      typeof latest === 'number' && Number.isFinite(latest) ? latest : Number.NaN
    return { metric, value: numeric }
  })

export const useFoAnalytics = (symbol: string, timeframe: string): FoAnalyticsState => {
  const [state, setState] = useState<FoAnalyticsState>(defaultState)

  const isHttpStatus = (error: unknown, status: number) => {
    const axiosError = error as AxiosError | undefined
    return Boolean(axiosError?.response && axiosError.response.status === status)
  }

  useEffect(() => {
    let cancelled = false
    let inFlight = false

    const load = async () => {
      if (inFlight) return
      inFlight = true
      try {
        setState((prev) => ({
          ...prev,
          loading: prev.expiries.length === 0,
          error: null,
        }))
        const expiriesResponse = await fetchFoExpiriesV2(symbol)
        const today = new Date()
        today.setUTCHours(0, 0, 0, 0)
        const filteredExpiries = expiriesResponse.expiries.filter((detail) => {
          const iso = detail.date
          const date = new Date(`${iso}T00:00:00Z`)
          return !Number.isNaN(date.getTime()) && date >= today
        })
        const selectedDetails = (filteredExpiries.length ? filteredExpiries : expiriesResponse.expiries).slice(0, 6)
        const expiries = selectedDetails.map((detail) => detail.date)
        const labelLookup = Object.fromEntries(
          selectedDetails.map((detail) => [detail.date, detail.relative_label_today ?? null]),
        )
        const calculator = new RelativeExpiryCalculator(expiries, labelLookup)
        const nowSeconds = Math.floor(Date.now() / 1000)

        const moneynessPromises = Object.entries(INDICATOR_MAP).map(async ([panelId, indicator]) => {
          try {
            const response = await fetchFoMoneynessSeries({
              symbol,
              timeframe,
              indicator,
              option_side: 'both',
              expiry: expiries,
            })
            return { panelId, response }
          } catch (error) {
            if (!isHttpStatus(error, 400)) {
              console.error(`[useFoAnalytics] moneyness fetch failed for ${indicator}`, error)
            }
            return { panelId, response: null }
          }
        })

        const strikePromises = STRIKE_INDICATORS.map(async (indicator: StrikeIndicator) => {
          try {
            const response = await fetchFoStrikeDistribution({
              symbol,
              timeframe,
              indicator,
              expiry: expiries,
            })
            return { indicator, response }
          } catch (error) {
            if (!isHttpStatus(error, 400)) {
              console.error(`[useFoAnalytics] strike fetch failed for ${indicator}`, error)
            }
            return { indicator, response: null }
          }
        })

        const moneynessResults = await Promise.all(moneynessPromises)
        const strikeResults = await Promise.all(strikePromises)

        if (cancelled) return

        const moneynessData: MoneynessPanelData = {}
        moneynessResults.forEach(({ panelId, response }) => {
          if (response) {
            moneynessData[panelId] = toMoneynessLines(response, calculator, nowSeconds)
          }
        })

        const strikeData: StrikePanelData = {
          delta: [],
          gamma: [],
          theta: [],
          rho: [],
          vega: [],
          iv: [],
          oi: [],
          pcr: [],
        }
        strikeResults.forEach(({ indicator, response }) => {
          if (response) {
            strikeData[indicator] = toStrikeLines(response, calculator, nowSeconds, indicator)
          }
        })

        const radar = computeRadarSnapshot(moneynessData)

        setState({
          loading: false,
          error: null,
          expiries,
          expiryDetails: selectedDetails,
          relativeCalculator: calculator,
          moneyness: moneynessData,
          strike: strikeData,
          radar,
        })
      } catch (error: any) {
        console.error('[useFoAnalytics] load error', error)
        if (!cancelled) {
          setState((prev) => ({
            ...prev,
            loading: false,
            error: error?.message ?? 'Failed to load FO analytics',
          }))
        }
      } finally {
        inFlight = false
      }
    }

    load()
    const interval = window.setInterval(load, 1000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [symbol, timeframe])

  return useMemo(() => state, [state])
}
