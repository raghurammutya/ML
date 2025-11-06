import React, { useEffect, useMemo, useState } from 'react'
import { ResponsiveContainer, AreaChart, Area, YAxis, XAxis, ReferenceLine } from 'recharts'
import styles from './MiniChartsPanel.module.css'
import { useMonitorSync } from '../../components/nifty-monitor/MonitorSyncContext'
import {
  PANEL_TEMPLATES,
  PANEL_GROUPS,
  fetchHistoryBars,
  HistoryBar,
  ChartPoint,
  nearestPoint,
} from './analytics'
import { classNames } from '../../utils/classNames'
import type { MoneynessPanelData } from '../../hooks/useFoAnalytics'

export interface MiniChartsPanelProps {
  symbol: string
  timeframe: string
  chartWidth: number
  variant?: 'default' | 'compact'
  offsetLeft?: number
  panels?: MoneynessPanelData | null
  loading?: boolean
  visibleExpiries?: string[]
  visibleMoneyness?: string[]
}

interface PanelState {
  chartHeight: number
  collapsed: boolean
}

type PanelStates = Record<string, PanelState>
type PanelOrder = Record<string, string[]>
type GroupCollapseState = Record<string, boolean>

const MiniChartsPanel: React.FC<MiniChartsPanelProps> = ({
  symbol,
  timeframe,
  chartWidth,
  variant = 'default',
  offsetLeft = 0,
  panels,
  loading = false,
  visibleExpiries,
  visibleMoneyness,
}) => {
  const { timeRange, crosshairTime } = useMonitorSync()
  const [bars, setBars] = useState<HistoryBar[]>([])
  const [panelStates, setPanelStates] = useState<PanelStates>(() =>
    Object.fromEntries(
      PANEL_TEMPLATES.map((panel) => [
        panel.id,
        {
          chartHeight: 160,
          collapsed: false,
        } satisfies PanelState,
      ]),
    ),
  )
  const [panelOrder, setPanelOrder] = useState<PanelOrder>(() =>
    Object.fromEntries(PANEL_GROUPS.map((group) => [group.id, [...group.panelIds]])),
  )
  const [collapsedGroups, setCollapsedGroups] = useState<GroupCollapseState>({})
  const expiryFilter = useMemo(
    () => (visibleExpiries && visibleExpiries.length ? new Set(visibleExpiries) : null),
    [visibleExpiries],
  )
  const moneynessFilter = useMemo(
    () => (visibleMoneyness && visibleMoneyness.length ? new Set(visibleMoneyness) : null),
    [visibleMoneyness],
  )

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const data = await fetchHistoryBars(symbol, timeframe)
        if (!cancelled) {
          setBars(data)
        }
      } catch (err) {
        console.error('Failed to load analytics history', err)
        if (!cancelled) setBars([])
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [symbol, timeframe])

  const analyticsSeriesMap = useMemo(() => {
    if (!panels) return null
    const map: Record<string, ChartPoint[]> = {}
    PANEL_TEMPLATES.forEach((template) => {
      const lines = panels[template.id] ?? []
      const filtered = lines.filter((line) => {
        const expiryOk = !expiryFilter || expiryFilter.has(line.expiry)
        const bucketOk = !moneynessFilter || moneynessFilter.has(line.bucket)
        return expiryOk && bucketOk
      })
      if (!filtered.length) {
        map[template.id] = []
        return
      }
      const aggregated = new Map<number, { sum: number; count: number }>()
      filtered.forEach((line) => {
        line.points.forEach((point) => {
          if (typeof point.value !== 'number' || !Number.isFinite(point.value)) return
          const current = aggregated.get(point.time) ?? { sum: 0, count: 0 }
          current.sum += point.value
          current.count += 1
          aggregated.set(point.time, current)
        })
      })
      const series = Array.from(aggregated.entries())
        .map(([time, { sum, count }]) => ({
          time,
          value: count > 0 ? sum / count : null,
        }))
        .sort((a, b) => a.time - b.time)
      map[template.id] = series
    })
    return map
  }, [panels, expiryFilter, moneynessFilter])

  const seriesMap = useMemo(() => {
    if (analyticsSeriesMap) return analyticsSeriesMap
    const map: Record<string, ChartPoint[]> = {}
    PANEL_TEMPLATES.forEach((template) => {
      map[template.id] = bars.map((bar, index, array) => ({
        time: bar.time,
        value: template.compute(bar, index, array),
      }))
    })
    return map
  }, [analyticsSeriesMap, bars])

  const wrapperStyle = {
    '--chart-width': `${chartWidth}px`,
    '--chart-offset-left': `${offsetLeft}px`,
  } as React.CSSProperties

  const toggleCollapse = (id: string) => {
    setPanelStates((prev) => ({
      ...prev,
      [id]: {
        ...prev[id],
        collapsed: !prev[id]?.collapsed,
      },
    }))
  }

  const changeHeight = (id: string, height: number) => {
    setPanelStates((prev) => ({
      ...prev,
      [id]: {
        ...prev[id],
        chartHeight: height,
      },
    }))
  }

  const movePanel = (groupId: string, id: string, direction: -1 | 1) => {
    setPanelOrder((prev) => {
      const currentOrder = prev[groupId] ?? []
      const index = currentOrder.indexOf(id)
      if (index < 0) return prev
      const nextIndex = index + direction
      if (nextIndex < 0 || nextIndex >= currentOrder.length) return prev
      const updated = [...currentOrder]
      const [removed] = updated.splice(index, 1)
      updated.splice(nextIndex, 0, removed)
      return {
        ...prev,
        [groupId]: updated,
      }
    })
  }

  const toggleGroup = (groupId: string) => {
    setCollapsedGroups((prev) => ({
      ...prev,
      [groupId]: !prev[groupId],
    }))
  }

  if (!PANEL_TEMPLATES.length) return null

  const showEmptyState =
    Boolean(panels) &&
    !loading &&
    PANEL_TEMPLATES.every((template) => (analyticsSeriesMap?.[template.id] ?? []).length === 0)

  return (
    <div className={classNames(styles.wrapper, variant === 'compact' && styles.compact)} style={wrapperStyle}>
      {showEmptyState && (
        <div className={styles.empty}>
          No analytics available for the selected filters.
        </div>
      )}
      {PANEL_GROUPS.map((group) => {
        const orderedPanels = panelOrder[group.id] ?? group.panelIds
        const groupCollapsed = collapsedGroups[group.id] ?? false

        return (
          <section key={group.id} className={styles.group}>
            <div className={styles.groupHeader}>
              <div className={styles.groupTitleBlock}>
                <h2>{group.title}</h2>
                <p>{group.subtitle}</p>
              </div>
              <button
                type="button"
                className={styles.groupToggle}
                onClick={() => toggleGroup(group.id)}
                aria-expanded={!groupCollapsed}
              >
                {groupCollapsed ? 'Expand' : 'Collapse'}
              </button>
            </div>

            {!groupCollapsed && (
              <div className={styles.panelColumn}>
                {orderedPanels.map((panelId, index) => {
                  const template = PANEL_TEMPLATES.find((panel) => panel.id === panelId)
                  if (!template) return null
                  const series = seriesMap[panelId] ?? []
                  const filtered =
                    timeRange && timeRange.from && timeRange.to
                      ? series.filter((point) => point.time >= timeRange.from && point.time <= timeRange.to)
                      : series
                  const displaySeries = filtered.length ? filtered : series
                  const activePoint = nearestPoint(displaySeries, crosshairTime)
                  const pointTime = activePoint?.time ?? null
                  const matchedBar = pointTime != null && bars.length
                    ? bars.reduce<HistoryBar>((best, bar) =>
                        Math.abs(bar.time - pointTime) < Math.abs(best.time - pointTime) ? bar : best,
                      bars[0])
                    : null
                  const valueColor = matchedBar
                    ? matchedBar.close >= matchedBar.open
                      ? '#26a69a'
                      : '#ef5350'
                    : template.color
                  const displayValue = template.formatter(activePoint?.value ?? null)
                  const state = panelStates[panelId] ?? { chartHeight: 160, collapsed: false }
                  const panelStyle = {
                    '--panel-chart-height': `${Math.max(state.chartHeight, 60)}px`,
                  } as React.CSSProperties

                  return (
                    <div
                      key={panelId}
                      className={classNames(styles.panel, state.collapsed && styles.collapsed)}
                      style={panelStyle}
                    >
                      <div className={styles.header}>
                        <div className={styles.title}>
                          <h3>{template.label}</h3>
                          {template.label !== template.title && (
                            <span className={styles.subtitle}>{template.title}</span>
                          )}
                          <span className={styles.value} style={{ color: valueColor }}>
                            {displayValue}
                          </span>
                        </div>
                        <div className={styles.controls}>
                          <button
                            className={styles.button}
                            type="button"
                            onClick={() => movePanel(group.id, panelId, -1)}
                            disabled={index === 0}
                            aria-label="Move panel up"
                          >
                            ↑
                          </button>
                          <button
                            className={styles.button}
                            type="button"
                            onClick={() => movePanel(group.id, panelId, 1)}
                            disabled={index === orderedPanels.length - 1}
                            aria-label="Move panel down"
                          >
                            ↓
                          </button>
                          <button
                            className={styles.button}
                            type="button"
                            onClick={() => toggleCollapse(panelId)}
                            aria-label={state.collapsed ? 'Expand panel' : 'Collapse panel'}
                          >
                            {state.collapsed ? 'Show' : 'Hide'}
                          </button>
                        </div>
                      </div>

                      {!state.collapsed && (
                        <>
                          <div className={styles.chart}>
                            <ResponsiveContainer width="100%" height="100%">
                              <AreaChart data={displaySeries} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                                <XAxis
                                  dataKey="time"
                                  type="number"
                                  domain={[
                                    timeRange ? timeRange.from : 'auto',
                                    timeRange ? timeRange.to : 'auto',
                                  ]}
                                  hide
                                />
                                <YAxis
                                  dataKey="value"
                                  orientation="right"
                                  stroke="rgba(148, 163, 184, 0.8)"
                                  width={56}
                                  domain={['auto', 'auto']}
                                  tick={{ fill: 'rgba(148, 163, 184, 0.8)', fontSize: 11 }}
                                />
                                {typeof crosshairTime === 'number' && (
                                  <ReferenceLine x={crosshairTime} stroke="#26a69a" strokeDasharray="4 4" />
                                )}
                                <Area
                                  type="monotone"
                                  dataKey="value"
                                  stroke={template.color}
                                  fill={template.color}
                                  fillOpacity={0.22}
                                  isAnimationActive={false}
                                  dot={false}
                                  strokeWidth={1.8}
                                />
                              </AreaChart>
                            </ResponsiveContainer>
                          </div>
                          <div className={styles.sliderRow}>
                            <span>Height</span>
                            <input
                              type="range"
                              min={60}
                              max={220}
                              step={10}
                              value={state.chartHeight}
                              onChange={(event) => changeHeight(panelId, Number(event.target.value))}
                            />
                          </div>
                        </>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </section>
        )
      })}
    </div>
  )
}

export default MiniChartsPanel
