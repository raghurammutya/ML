import React, { useEffect, useMemo, useState } from 'react'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ReferenceLine,
  Tooltip,
} from 'recharts'
import styles from './SideTabsPanel.module.css'
import { useMonitorSync } from '../../components/nifty-monitor/MonitorSyncContext'
import { fetchHistoryBars, HistoryBar } from './analytics'
import type { FoAnalyticsState, StrikeSeriesLine } from '../../hooks/useFoAnalytics'

type Side = 'left' | 'right'

type PanelId = 'Delta' | 'Gamma' | 'Theta' | 'Rho' | 'Vega' | 'IV' | 'OI' | 'PCR'

interface PanelConfig {
  id: PanelId
  label: string
  indicator: keyof FoAnalyticsState['strike']
  formatter: (value: number | null) => string
}

const PANEL_CONFIG: PanelConfig[] = [
  {
    id: 'Delta',
    label: 'Delta',
    indicator: 'delta',
    formatter: (value) => (value != null ? value.toFixed(3) : '—'),
  },
  {
    id: 'Gamma',
    label: 'Gamma',
    indicator: 'gamma',
    formatter: (value) => (value != null ? value.toFixed(4) : '—'),
  },
  {
    id: 'Theta',
    label: 'Theta',
    indicator: 'theta',
    formatter: (value) => (value != null ? value.toFixed(2) : '—'),
  },
  {
    id: 'Rho',
    label: 'Rho',
    indicator: 'rho',
    formatter: (value) => (value != null ? value.toFixed(3) : '—'),
  },
  {
    id: 'Vega',
    label: 'Vega',
    indicator: 'vega',
    formatter: (value) => (value != null ? value.toFixed(3) : '—'),
  },
  {
    id: 'IV',
    label: 'IV',
    indicator: 'iv',
    formatter: (value) => (value != null ? `${value.toFixed(2)}%` : '—'),
  },
  {
    id: 'OI',
    label: 'OI',
    indicator: 'oi',
    formatter: (value) => (value != null ? value.toFixed(0) : '—'),
  },
  {
    id: 'PCR',
    label: 'PCR',
    indicator: 'pcr',
    formatter: (value) => (value != null ? value.toFixed(2) : '—'),
  },
]

interface StrikePoint {
  strike: number
  value: number | null
}

interface DecoratedLine {
  label: string
  color: string
  points: StrikePoint[]
}

interface SideTabsPanelProps {
  symbol: string
  timeframe: string
  title: string
  side: Side
  analytics: FoAnalyticsState
  chartHeight?: number
  visibleExpiries?: string[]
  visibleMoneyness?: string[]
}

const FALLBACK_COLORS = ['#60a5fa', '#f97316', '#a855f7', '#34d399']

const findClosestPoint = (points: StrikePoint[], targetStrike: number | null): StrikePoint | null => {
  if (!points.length) return null
  if (targetStrike == null) return points[points.length - 1]
  let closest = points[0]
  let bestDiff = Math.abs(points[0].strike - targetStrike)
  for (let index = 1; index < points.length; index += 1) {
    const candidate = points[index]
    const diff = Math.abs(candidate.strike - targetStrike)
    if (diff < bestDiff) {
      closest = candidate
      bestDiff = diff
    }
  }
  return closest
}

const computeStrikeGap = (points: StrikePoint[]): number => {
  if (points.length < 2) return 0
  const ordered = Array.from(new Set(points.map((point) => point.strike))).sort((a, b) => a - b)
  let minGap = Infinity
  for (let index = 1; index < ordered.length; index += 1) {
    const diff = ordered[index] - ordered[index - 1]
    if (diff > 0 && diff < minGap) {
      minGap = diff
    }
  }
  return Number.isFinite(minGap) ? minGap : 0
}

const resolveMoneynessBucket = (strike: number, atmStrike: number | null, strikeGap: number, side: Side): string => {
  if (atmStrike == null || !Number.isFinite(atmStrike) || strikeGap <= 0) {
    return 'ATM'
  }
  const diff = strike - atmStrike
  if (Math.abs(diff) <= strikeGap * 0.6) {
    return 'ATM'
  }
  const steps = Math.max(1, Math.round(Math.abs(diff) / strikeGap))
  if (side === 'left') {
    return diff >= 0 ? `OTM${steps}` : `ITM${steps}`
  }
  return diff <= 0 ? `OTM${steps}` : `ITM${steps}`
}

const decorateLines = (lines: StrikeSeriesLine[], side: Side, moneynessFilter?: Set<string>): DecoratedLine[] =>
  lines
    .map((line) => {
      const basePoints = side === 'left' ? line.calls : line.puts
      const points = basePoints
        .map((point) => ({ strike: point.strike, value: point.value }))
        .filter((point) => point.value != null)
      if (!points.length) {
        return {
          label: line.label ?? line.expiry,
          color: line.color,
          points,
        }
      }
      const strikeGap = computeStrikeGap(points)
      const atmReference =
        line.metadata?.atm_strike ??
        points[Math.floor(points.length / 2)]?.strike ??
        null
      const filteredPoints =
        moneynessFilter && moneynessFilter.size
          ? points.filter((point) => moneynessFilter.has(resolveMoneynessBucket(point.strike, atmReference, strikeGap, side)))
          : points
      return {
        label: line.label ?? line.expiry,
        color: line.color,
        points: filteredPoints,
      }
    })
    .filter((line) => line.points.length > 0)

const buildFallbackDecoratedLines = (expiries: string[], side: Side): DecoratedLine[] => {
  const source = expiries.length ? expiries : ['Synthetic']
  return source.slice(0, 4).map((expiry, index) => {
    const baseStrike = 18000 + index * 120
    const points = Array.from({ length: 13 }, (_, pointIndex) => {
      const ratio = pointIndex / 12
      const strike = baseStrike + (pointIndex - 6) * 25
      const rawValue = -1 + ratio * 2
      const adjustedValue = side === 'right' ? rawValue * 0.85 : rawValue
      return {
        strike,
        value: adjustedValue,
      }
    })
    return {
      label: expiry,
      color: FALLBACK_COLORS[index % FALLBACK_COLORS.length],
      points,
    }
  })
}

const computeValueDomain = (lines: DecoratedLine[]): [number, number] => {
  const values = lines.flatMap((line) => line.points.map((point) => point.value ?? 0))
  if (!values.length) return [-1, 1]
  const min = Math.min(...values)
  const max = Math.max(...values)
  if (min === max) {
    const padding = Math.abs(min || 1) * 0.25
    return [min - padding, max + padding]
  }
  const padding = (max - min) * 0.12
  return [min - padding, max + padding]
}

const computeStrikeDomain = (
  lines: DecoratedLine[],
  priceRange: { min: number; max: number } | null,
): [number, number] => {
  if (priceRange) {
    return [priceRange.min, priceRange.max]
  }
  const strikes = lines.flatMap((line) => line.points.map((point) => point.strike))
  if (!strikes.length) return [0, 1]
  const min = Math.min(...strikes)
  const max = Math.max(...strikes)
  if (min === max) {
    return [min - 25, max + 25]
  }
  return [min, max]
}

const SideTabsPanel: React.FC<SideTabsPanelProps> = ({
  symbol,
  timeframe,
  title,
  side,
  analytics,
  chartHeight,
  visibleExpiries,
  visibleMoneyness,
}) => {
  const { crosshairTime, priceRange, crosshairPrice } = useMonitorSync()
  const [bars, setBars] = useState<HistoryBar[]>([])
  const [activeId, setActiveId] = useState<PanelId>(PANEL_CONFIG[0].id)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const data = await fetchHistoryBars(symbol, timeframe)
        if (!cancelled) {
          setBars(data)
        }
      } catch (err) {
        console.error('Failed to load history bars', err)
        if (!cancelled) setBars([])
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [symbol, timeframe])

  const activeConfig = useMemo(
    () => PANEL_CONFIG.find((panel) => panel.id === activeId) ?? PANEL_CONFIG[0],
    [activeId],
  )

  const strikeLines = analytics.strike[activeConfig.indicator] ?? []
  const filteredStrikeLines = useMemo(() => {
    if (!visibleExpiries || visibleExpiries.length === 0) {
      return strikeLines
    }
    const allowed = new Set(visibleExpiries)
    return strikeLines.filter((line) => allowed.has(line.expiry))
  }, [strikeLines, visibleExpiries])

  const decoratedLines = useMemo(
    () =>
      decorateLines(
        filteredStrikeLines,
        side,
        visibleMoneyness && visibleMoneyness.length ? new Set(visibleMoneyness) : undefined,
      ),
    [filteredStrikeLines, side, visibleMoneyness],
  )

  const fallbackLines = useMemo(() => {
    const sourceExpiries = visibleExpiries && visibleExpiries.length ? visibleExpiries : analytics.expiries
    return buildFallbackDecoratedLines(sourceExpiries, side)
  }, [analytics.expiries, side, visibleExpiries])

  const activeLines = decoratedLines.length ? decoratedLines : fallbackLines

  const strikeDomain = useMemo(
    () => computeStrikeDomain(activeLines, priceRange),
    [activeLines, priceRange],
  )

  const valueDomain = useMemo(
    () => computeValueDomain(activeLines),
    [activeLines],
  )

  const targetPoint = useMemo(() => {
    const primaryLine = activeLines[0]
    if (!primaryLine) return null
    const referenceStrike =
      typeof crosshairPrice === 'number'
        ? crosshairPrice
        : primaryLine.points[primaryLine.points.length - 1]?.strike ?? null
    return findClosestPoint(primaryLine.points, referenceStrike)
  }, [activeLines, crosshairPrice])

  const displayValue = useMemo(
    () => activeConfig.formatter(targetPoint?.value ?? null),
    [activeConfig, targetPoint],
  )

  const matchingBar = useMemo(() => {
    if (!bars.length) return null
    if (typeof crosshairTime === 'number') {
      let closest = bars[0]
      let bestDiff = Math.abs(bars[0].time - crosshairTime)
      for (let index = 1; index < bars.length; index += 1) {
        const candidate = bars[index]
        const diff = Math.abs(candidate.time - crosshairTime)
        if (diff < bestDiff) {
          closest = candidate
          bestDiff = diff
        }
      }
      return closest
    }
      return bars[bars.length - 1]
  }, [bars, crosshairTime])

  const valueColor = matchingBar
    ? matchingBar.close >= matchingBar.open
      ? '#26a69a'
      : '#ef5350'
    : activeLines[0]?.color ?? '#cbd5f5'

  const containerClass = `${styles.container} ${side === 'right' ? styles.wrapperRight : styles.wrapperLeft}`
  const containerStyle = chartHeight ? { minHeight: chartHeight + 110 } : undefined
  const chartStyle = chartHeight ? { height: chartHeight } : undefined

  return (
    <div className={containerClass} style={containerStyle}>
      <div className={styles.title}>{title}</div>
      <div className={styles.tabs}>
        <div className={styles.tabList}>
          {PANEL_CONFIG.map((panel) => (
            <button
              key={panel.id}
              type="button"
              className={`${styles.tabButton} ${panel.id === activeId ? styles.tabButtonActive : ''}`}
              onClick={() => setActiveId(panel.id)}
            >
              {panel.label}
            </button>
          ))}
        </div>
        <div className={`${styles.chartHolder} ${side === 'right' ? styles.chartHolderRight : styles.chartHolderLeft}`} style={chartStyle}>
          {activeLines.length > 0 && (
            <div className={styles.overlayTop}>
              <div className={styles.valueLine} style={{ color: valueColor }}>
                <span className={styles.valueStrike}>
                  {targetPoint?.strike != null ? Math.round(targetPoint.strike).toLocaleString('en-IN') : '—'}
                </span>
                <span className={styles.valueMetric}>{activeConfig.label}</span>
                <span className={styles.valueNumber}>{displayValue}</span>
              </div>
            </div>
          )}

          {activeLines.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart layout="vertical" margin={{ top: 2, right: 4, bottom: 2, left: 6 }}>
                <CartesianGrid stroke="rgba(148, 163, 184, 0.12)" horizontal={false} />
                <XAxis
                  type="number"
                  domain={valueDomain}
                  tick={{ fill: 'rgba(148, 163, 184, 0.75)', fontSize: 11 }}
                  axisLine={{ stroke: 'rgba(148, 163, 184, 0.18)' }}
                  tickLine={false}
                />
                <YAxis
                  type="number"
                  domain={strikeDomain}
                  dataKey="strike"
                  orientation={side === 'left' ? 'left' : 'right'}
                  stroke="rgba(148, 163, 184, 0.65)"
                  tick={{ fill: 'rgba(148, 163, 184, 0.75)', fontSize: 11 }}
                  axisLine={{ stroke: 'rgba(148, 163, 184, 0.18)' }}
                  tickLine={false}
                  width={46}
                  reversed
                />
                {typeof crosshairPrice === 'number' && (
                  <ReferenceLine
                    y={crosshairPrice}
                    stroke="rgba(38, 166, 154, 0.75)"
                    strokeDasharray="4 4"
                  />
                )}
                <Tooltip
                  isAnimationActive={false}
                  contentStyle={{
                    background: 'rgba(15, 23, 42, 0.9)',
                    border: '1px solid rgba(148, 163, 184, 0.3)',
                    borderRadius: 12,
                    padding: '8px 12px',
                    color: '#f8fafc',
                  }}
                  cursor={{ stroke: 'rgba(148, 163, 184, 0.25)', strokeDasharray: '4 4' }}
                  formatter={(value: any, name) => [
                    activeConfig.formatter(typeof value === 'number' ? value : null),
                    String(name ?? activeConfig.label),
                  ]}
                  labelFormatter={(strike) =>
                    `Strike: ${Number(strike).toLocaleString('en-IN', {
                      maximumFractionDigits: 0,
                    })}`
                  }
                />
                {activeLines.map((line) => (
                  <Line
                    key={line.label}
                    type="monotone"
                    data={line.points}
                    dataKey="value"
                    stroke={line.color}
                    strokeWidth={2}
                    dot={false}
                    name={line.label}
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className={styles.emptyState}>
              {analytics.loading ? 'Loading analytics…' : 'Awaiting strike distribution'}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default SideTabsPanel
