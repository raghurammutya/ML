import { createContext, useContext, useState, PropsWithChildren } from 'react'

interface PriceRange {
  min: number
  max: number
}

interface TimeRange {
  from: number
  to: number
}

interface MonitorSyncContextValue {
  timeRange: TimeRange | null
  crosshairTime: number | null
  priceRange: PriceRange | null
  setTimeRange: (range: TimeRange | null) => void
  setCrosshairTime: (time: number | null) => void
  setPriceRange: (range: PriceRange | null) => void
  crosshairRatio: number | null
  setCrosshairRatio: (ratio: number | null) => void
  crosshairWidth: number | null
  setCrosshairWidth: (width: number | null) => void
  crosshairPrice: number | null
  setCrosshairPrice: (price: number | null) => void
}

const MonitorSyncContext = createContext<MonitorSyncContextValue>({
  timeRange: null,
  crosshairTime: null,
  priceRange: null,
  setTimeRange: () => undefined,
  setCrosshairTime: () => undefined,
  setPriceRange: () => undefined,
  crosshairRatio: null,
  setCrosshairRatio: () => undefined,
  crosshairWidth: null,
  setCrosshairWidth: () => undefined,
  crosshairPrice: null,
  setCrosshairPrice: () => undefined,
})

export const MonitorSyncProvider = ({ children }: PropsWithChildren) => {
  const [timeRange, setTimeRange] = useState<TimeRange | null>(null)
  const [crosshairTime, setCrosshairTime] = useState<number | null>(null)
  const [priceRange, setPriceRange] = useState<PriceRange | null>(null)
  const [crosshairRatio, setCrosshairRatio] = useState<number | null>(null)
  const [crosshairWidth, setCrosshairWidth] = useState<number | null>(null)
  const [crosshairPrice, setCrosshairPrice] = useState<number | null>(null)

  return (
    <MonitorSyncContext.Provider
      value={{
        timeRange,
        setTimeRange,
        crosshairTime,
        setCrosshairTime,
        priceRange,
        setPriceRange,
        crosshairRatio,
        setCrosshairRatio,
        crosshairWidth,
        setCrosshairWidth,
        crosshairPrice,
        setCrosshairPrice,
      }}
    >
      {children}
    </MonitorSyncContext.Provider>
  )
}

export const useMonitorSync = () => useContext(MonitorSyncContext)
