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
}

const MonitorSyncContext = createContext<MonitorSyncContextValue>({
  timeRange: null,
  crosshairTime: null,
  priceRange: null,
  setTimeRange: () => undefined,
  setCrosshairTime: () => undefined,
  setPriceRange: () => undefined,
})

export const MonitorSyncProvider = ({ children }: PropsWithChildren) => {
  const [timeRange, setTimeRange] = useState<TimeRange | null>(null)
  const [crosshairTime, setCrosshairTime] = useState<number | null>(null)
  const [priceRange, setPriceRange] = useState<PriceRange | null>(null)

  return (
    <MonitorSyncContext.Provider value={{ timeRange, setTimeRange, crosshairTime, setCrosshairTime, priceRange, setPriceRange }}>
      {children}
    </MonitorSyncContext.Provider>
  )
}

export const useMonitorSync = () => useContext(MonitorSyncContext)
