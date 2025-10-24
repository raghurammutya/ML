import { useEffect, useRef } from 'react'
import { IChartApi, ISeriesApi, LineData, Time } from 'lightweight-charts'
import { CPRPoint, IndicatorSettings } from '../components/IndicatorPanel'

interface CPRSeries {
  pivot: ISeriesApi<'Line'> | null
  bc: ISeriesApi<'Line'> | null
  tc: ISeriesApi<'Line'> | null
  r1: ISeriesApi<'Line'> | null
  r2: ISeriesApi<'Line'> | null
  s1: ISeriesApi<'Line'> | null
  s2: ISeriesApi<'Line'> | null
}

export const useCPRIndicator = (
  chartRef: React.RefObject<IChartApi | null>,
  settings: IndicatorSettings
) => {
  const cprSeriesRef = useRef<CPRSeries>({
    pivot: null,
    bc: null,
    tc: null,
    r1: null,
    r2: null,
    s1: null,
    s2: null
  })

  // Create CPR series when enabled
  useEffect(() => {
    if (!chartRef.current) return

    if (settings.enabled) {
      createCPRSeries()
    } else {
      removeCPRSeries()
    }

    return () => {
      removeCPRSeries()
    }
  }, [settings.enabled])

  // Update series styles when settings change
  useEffect(() => {
    if (settings.enabled && cprSeriesRef.current.pivot) {
      updateSeriesStyles()
    }
  }, [
    settings.pivot_color,
    settings.bc_color,
    settings.tc_color,
    settings.resistance_color,
    settings.support_color,
    settings.line_width,
    settings.line_style
  ])

  const createCPRSeries = () => {
    if (!chartRef.current) return

    const chart = chartRef.current
    
    // Convert line style
    const lineStyle = settings.line_style === 'dashed' ? 2 : 
                     settings.line_style === 'dotted' ? 3 : 0

    // Create series for each CPR level
    cprSeriesRef.current = {
      pivot: chart.addLineSeries({
        color: settings.pivot_color,
        lineWidth: settings.line_width as any,
        lineStyle: lineStyle as any,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        title: 'Pivot'
      }),
      bc: chart.addLineSeries({
        color: settings.bc_color,
        lineWidth: settings.line_width as any,
        lineStyle: lineStyle as any,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        title: 'BC'
      }),
      tc: chart.addLineSeries({
        color: settings.tc_color,
        lineWidth: settings.line_width as any,
        lineStyle: lineStyle as any,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        title: 'TC'
      }),
      r1: chart.addLineSeries({
        color: settings.resistance_color,
        lineWidth: settings.line_width as any,
        lineStyle: lineStyle as any,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        title: 'R1'
      }),
      r2: chart.addLineSeries({
        color: settings.resistance_color,
        lineWidth: settings.line_width as any,
        lineStyle: lineStyle as any,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        title: 'R2'
      }),
      s1: chart.addLineSeries({
        color: settings.support_color,
        lineWidth: settings.line_width as any,
        lineStyle: lineStyle as any,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        title: 'S1'
      }),
      s2: chart.addLineSeries({
        color: settings.support_color,
        lineWidth: settings.line_width as any,
        lineStyle: lineStyle as any,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        title: 'S2'
      })
    }
  }

  const removeCPRSeries = () => {
    if (!chartRef.current) return

    const chart = chartRef.current
    const series = cprSeriesRef.current

    Object.values(series).forEach(s => {
      if (s) {
        chart.removeSeries(s)
      }
    })

    cprSeriesRef.current = {
      pivot: null,
      bc: null,
      tc: null,
      r1: null,
      r2: null,
      s1: null,
      s2: null
    }
  }

  const updateSeriesStyles = () => {
    const series = cprSeriesRef.current
    const lineStyle = settings.line_style === 'dashed' ? 2 : 
                     settings.line_style === 'dotted' ? 3 : 0

    if (series.pivot) {
      series.pivot.applyOptions({
        color: settings.pivot_color,
        lineWidth: settings.line_width as any,
        lineStyle: lineStyle as any
      })
    }
    if (series.bc) {
      series.bc.applyOptions({
        color: settings.bc_color,
        lineWidth: settings.line_width as any,
        lineStyle: lineStyle as any
      })
    }
    if (series.tc) {
      series.tc.applyOptions({
        color: settings.tc_color,
        lineWidth: settings.line_width as any,
        lineStyle: lineStyle as any
      })
    }
    if (series.r1) {
      series.r1.applyOptions({
        color: settings.resistance_color,
        lineWidth: settings.line_width as any,
        lineStyle: lineStyle as any
      })
    }
    if (series.r2) {
      series.r2.applyOptions({
        color: settings.resistance_color,
        lineWidth: settings.line_width as any,
        lineStyle: lineStyle as any
      })
    }
    if (series.s1) {
      series.s1.applyOptions({
        color: settings.support_color,
        lineWidth: settings.line_width as any,
        lineStyle: lineStyle as any
      })
    }
    if (series.s2) {
      series.s2.applyOptions({
        color: settings.support_color,
        lineWidth: settings.line_width as any,
        lineStyle: lineStyle as any
      })
    }
  }

  const updateCPRData = (cprData: CPRPoint[]) => {
    if (!settings.enabled || !cprSeriesRef.current.pivot) return

    // Convert CPR data to line series format
    const pivotData: LineData[] = []
    const bcData: LineData[] = []
    const tcData: LineData[] = []
    const r1Data: LineData[] = []
    const r2Data: LineData[] = []
    const s1Data: LineData[] = []
    const s2Data: LineData[] = []

    cprData.forEach(point => {
      const time = point.time as Time
      pivotData.push({ time, value: point.pivot })
      bcData.push({ time, value: point.bc })
      tcData.push({ time, value: point.tc })
      r1Data.push({ time, value: point.r1 })
      r2Data.push({ time, value: point.r2 })
      s1Data.push({ time, value: point.s1 })
      s2Data.push({ time, value: point.s2 })
    })

    // Update each series
    const series = cprSeriesRef.current
    if (series.pivot) series.pivot.setData(pivotData)
    if (series.bc) series.bc.setData(bcData)
    if (series.tc) series.tc.setData(tcData)
    if (series.r1) series.r1.setData(r1Data)
    if (series.r2) series.r2.setData(r2Data)
    if (series.s1) series.s1.setData(s1Data)
    if (series.s2) series.s2.setData(s2Data)
  }

  return {
    updateCPRData,
    removeCPRSeries
  }
}