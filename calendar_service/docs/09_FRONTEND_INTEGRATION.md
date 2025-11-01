# Calendar Service - Frontend Integration Guide

## Overview

This guide provides complete step-by-step instructions for integrating the Calendar Service v2.0 with your React frontend.

**Complexity**: Medium (3-4 hours)
**Files to Create**: 5
**Files to Modify**: 3
**Dependencies**: None (uses existing axios)

---

## 🎯 What You'll Build

### 1. Market Status Indicator in Header
```
┌─────────────────────────────────────────────────────────┐
│ [User] [Accounts] [Funds]    🟢 Market Open | 09:15-15:30│
└─────────────────────────────────────────────────────────┘
```

### 2. Holiday Calendar Widget (Optional)
```
┌──────────────────────────┐
│ Upcoming Holidays        │
├──────────────────────────┤
│ 📅 Nov 15 - Guru Nanak   │
│ 📅 Dec 25 - Christmas    │
│ 🎆 Nov 1 - Muhurat 18:15 │
└──────────────────────────┘
```

### 3. Special Session Alerts
```
⚠️ Special Trading Session Today
   Muhurat Trading: 18:15 - 19:15
```

---

## 📁 Files to Create

### File Structure
```
frontend/src/
├── services/
│   └── calendarApi.ts          ✨ NEW
├── hooks/
│   └── useMarketStatus.ts      ✨ NEW
├── components/
│   ├── MarketStatusBadge.tsx   ✨ NEW
│   ├── HolidayCalendar.tsx     ✨ NEW (optional)
│   └── GlobalHeader.tsx        📝 MODIFY
├── types/
│   └── calendar.ts             ✨ NEW
└── App.tsx                     📝 MODIFY
```

---

## 📝 Step-by-Step Implementation

### Step 1: Create TypeScript Types

**File**: `frontend/src/types/calendar.ts`

```typescript
// Calendar API Types
export interface MarketStatus {
  calendar_code: string
  date: string
  is_trading_day: boolean
  is_holiday: boolean
  is_weekend: boolean
  current_session: 'pre-market' | 'trading' | 'post-market' | 'closed'
  holiday_name: string | null
  session_start: string | null
  session_end: string | null
  next_trading_day: string | null
  // Special session fields (v2.0)
  is_special_session: boolean
  special_event_name: string | null
  event_type: 'special_hours' | 'early_close' | 'extended_hours' | null
}

export interface Holiday {
  date: string
  name: string
  category: string
  calendar_code: string
}

export interface CalendarType {
  code: string
  name: string
  description: string
  category: string
}

export interface HealthStatus {
  status: 'healthy' | 'unhealthy'
  timestamp: string
  database: string
  calendars_available: number
  cache_status: string
}

// UI State Types
export type MarketState = 'open' | 'closed' | 'pre-market' | 'post-market' | 'special' | 'unknown'

export interface MarketStatusDisplay {
  state: MarketState
  label: string
  color: 'green' | 'red' | 'yellow' | 'orange' | 'gray'
  icon: string
  hours?: string
  tooltip?: string
}
```

---

### Step 2: Create Calendar API Service

**File**: `frontend/src/services/calendarApi.ts`

```typescript
import axios from 'axios'
import { MarketStatus, Holiday, CalendarType, HealthStatus } from '../types/calendar'

// Use environment variable or default
const CALENDAR_BASE_URL = import.meta.env.VITE_CALENDAR_BASE_URL || '/calendar'

// Create axios instance
export const calendarApi = axios.create({
  baseURL: CALENDAR_BASE_URL,
  timeout: 10000, // 10 seconds
  headers: {
    'Content-Type': 'application/json'
  }
})

/**
 * Get current market status
 */
export const getMarketStatus = async (
  calendar: string = 'NSE',
  checkDate?: string
): Promise<MarketStatus> => {
  const params = new URLSearchParams()
  params.append('calendar', calendar)
  if (checkDate) {
    params.append('check_date', checkDate)
  }

  const response = await calendarApi.get<MarketStatus>(`/status?${params}`)
  return response.data
}

/**
 * Get list of holidays
 */
export const getHolidays = async (
  calendar: string = 'NSE',
  year?: number
): Promise<Holiday[]> => {
  const params = new URLSearchParams()
  params.append('calendar', calendar)
  if (year) {
    params.append('year', year.toString())
  }

  const response = await calendarApi.get<Holiday[]>(`/holidays?${params}`)
  return response.data
}

/**
 * Get next trading day
 */
export const getNextTradingDay = async (
  calendar: string = 'NSE',
  afterDate?: string
): Promise<{ calendar: string; after_date: string; next_trading_day: string; days_until: number }> => {
  const params = new URLSearchParams()
  params.append('calendar', calendar)
  if (afterDate) {
    params.append('after_date', afterDate)
  }

  const response = await calendarApi.get(`/next-trading-day?${params}`)
  return response.data
}

/**
 * Get all available calendars
 */
export const getCalendars = async (): Promise<CalendarType[]> => {
  const response = await calendarApi.get<CalendarType[]>('/calendars')
  return response.data
}

/**
 * Health check
 */
export const getCalendarHealth = async (): Promise<HealthStatus> => {
  const response = await calendarApi.get<HealthStatus>('/health')
  return response.data
}

/**
 * Helper: Format time for display
 */
export const formatTime = (time: string | null): string => {
  if (!time) return ''
  // Convert HH:MM:SS to HH:MM
  return time.substring(0, 5)
}

/**
 * Helper: Format date for display
 */
export const formatDate = (dateStr: string): string => {
  const date = new Date(dateStr)
  return new Intl.DateTimeFormat('en-IN', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  }).format(date)
}

/**
 * Helper: Get days until date
 */
export const getDaysUntil = (targetDate: string): number => {
  const target = new Date(targetDate)
  const now = new Date()
  const diffTime = target.getTime() - now.getTime()
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24))
}
```

---

### Step 3: Create Market Status Hook

**File**: `frontend/src/hooks/useMarketStatus.ts`

```typescript
import { useState, useEffect, useCallback } from 'react'
import { MarketStatus, MarketStatusDisplay, MarketState } from '../types/calendar'
import { getMarketStatus, formatTime } from '../services/calendarApi'

interface UseMarketStatusOptions {
  calendar?: string
  refreshInterval?: number // milliseconds
  enabled?: boolean
}

interface UseMarketStatusResult {
  status: MarketStatus | null
  display: MarketStatusDisplay
  loading: boolean
  error: Error | null
  refresh: () => Promise<void>
}

/**
 * Convert MarketStatus to display-friendly format
 */
function getMarketDisplay(status: MarketStatus | null): MarketStatusDisplay {
  if (!status) {
    return {
      state: 'unknown',
      label: 'Loading...',
      color: 'gray',
      icon: '⏳'
    }
  }

  // Special session handling
  if (status.is_special_session && status.special_event_name) {
    const hours = status.session_start && status.session_end
      ? `${formatTime(status.session_start)} - ${formatTime(status.session_end)}`
      : ''

    return {
      state: 'special',
      label: `Special Session: ${status.special_event_name}`,
      color: 'orange',
      icon: '🎆',
      hours,
      tooltip: `${status.special_event_name}\n${hours}`
    }
  }

  // Holiday
  if (status.is_holiday && status.holiday_name) {
    return {
      state: 'closed',
      label: `Holiday: ${status.holiday_name}`,
      color: 'red',
      icon: '📅',
      tooltip: `Market closed\nNext trading: ${status.next_trading_day || 'Unknown'}`
    }
  }

  // Weekend
  if (status.is_weekend && !status.is_trading_day) {
    return {
      state: 'closed',
      label: 'Market Closed (Weekend)',
      color: 'red',
      icon: '🔴',
      tooltip: `Next trading: ${status.next_trading_day || 'Unknown'}`
    }
  }

  // Trading day - check current session
  if (status.is_trading_day) {
    const hours = status.session_start && status.session_end
      ? `${formatTime(status.session_start)} - ${formatTime(status.session_end)}`
      : ''

    switch (status.current_session) {
      case 'trading':
        return {
          state: 'open',
          label: 'Market Open',
          color: 'green',
          icon: '🟢',
          hours,
          tooltip: `Trading: ${hours}`
        }

      case 'pre-market':
        return {
          state: 'pre-market',
          label: 'Pre-Market',
          color: 'yellow',
          icon: '🟡',
          hours,
          tooltip: `Opens at ${formatTime(status.session_start)}`
        }

      case 'post-market':
        return {
          state: 'post-market',
          label: 'Post-Market',
          color: 'yellow',
          icon: '🟡',
          hours,
          tooltip: `Closed at ${formatTime(status.session_end)}`
        }

      default:
        return {
          state: 'closed',
          label: 'Market Closed',
          color: 'red',
          icon: '🔴',
          hours,
          tooltip: `Trading hours: ${hours}`
        }
    }
  }

  // Default closed
  return {
    state: 'closed',
    label: 'Market Closed',
    color: 'red',
    icon: '🔴'
  }
}

/**
 * Hook to fetch and monitor market status
 */
export function useMarketStatus(options: UseMarketStatusOptions = {}): UseMarketStatusResult {
  const {
    calendar = 'NSE',
    refreshInterval = 60000, // 1 minute default
    enabled = true
  } = options

  const [status, setStatus] = useState<MarketStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  const fetchStatus = useCallback(async () => {
    if (!enabled) return

    try {
      setError(null)
      const data = await getMarketStatus(calendar)
      setStatus(data)
    } catch (err) {
      console.error('Failed to fetch market status:', err)
      setError(err instanceof Error ? err : new Error('Unknown error'))
    } finally {
      setLoading(false)
    }
  }, [calendar, enabled])

  // Initial fetch
  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  // Auto-refresh
  useEffect(() => {
    if (!enabled || !refreshInterval) return

    const interval = setInterval(fetchStatus, refreshInterval)
    return () => clearInterval(interval)
  }, [enabled, refreshInterval, fetchStatus])

  const display = getMarketDisplay(status)

  return {
    status,
    display,
    loading,
    error,
    refresh: fetchStatus
  }
}
```

---

### Step 4: Create Market Status Badge Component

**File**: `frontend/src/components/MarketStatusBadge.tsx`

```typescript
import React from 'react'
import { useMarketStatus } from '../hooks/useMarketStatus'
import './MarketStatusBadge.css'

interface MarketStatusBadgeProps {
  calendar?: string
  refreshInterval?: number
  showHours?: boolean
  compact?: boolean
}

const MarketStatusBadge: React.FC<MarketStatusBadgeProps> = ({
  calendar = 'NSE',
  refreshInterval = 60000,
  showHours = true,
  compact = false
}) => {
  const { display, loading, error, refresh } = useMarketStatus({
    calendar,
    refreshInterval,
    enabled: true
  })

  if (loading) {
    return (
      <div className="market-status-badge market-status-badge--loading">
        <span className="market-status-badge__icon">⏳</span>
        {!compact && <span className="market-status-badge__label">Loading...</span>}
      </div>
    )
  }

  if (error) {
    return (
      <div
        className="market-status-badge market-status-badge--error"
        onClick={refresh}
        title="Click to retry"
      >
        <span className="market-status-badge__icon">⚠️</span>
        {!compact && <span className="market-status-badge__label">Error</span>}
      </div>
    )
  }

  const colorClass = `market-status-badge--${display.color}`

  return (
    <div
      className={`market-status-badge ${colorClass}`}
      title={display.tooltip || display.label}
    >
      <span className="market-status-badge__icon">{display.icon}</span>
      {!compact && (
        <>
          <span className="market-status-badge__label">{display.label}</span>
          {showHours && display.hours && (
            <span className="market-status-badge__hours">{display.hours}</span>
          )}
        </>
      )}
    </div>
  )
}

export default MarketStatusBadge
```

**File**: `frontend/src/components/MarketStatusBadge.css`

```css
.market-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: default;
  transition: all 0.2s ease;
}

.market-status-badge__icon {
  font-size: 16px;
  line-height: 1;
}

.market-status-badge__label {
  line-height: 1;
}

.market-status-badge__hours {
  font-size: 12px;
  opacity: 0.8;
  margin-left: 4px;
}

/* Color variants */
.market-status-badge--green {
  background-color: rgba(34, 197, 94, 0.15);
  color: #22c55e;
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.market-status-badge--red {
  background-color: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.market-status-badge--yellow {
  background-color: rgba(234, 179, 8, 0.15);
  color: #eab308;
  border: 1px solid rgba(234, 179, 8, 0.3);
}

.market-status-badge--orange {
  background-color: rgba(249, 115, 22, 0.15);
  color: #f97316;
  border: 1px solid rgba(249, 115, 22, 0.3);
}

.market-status-badge--gray {
  background-color: rgba(156, 163, 175, 0.15);
  color: #9ca3af;
  border: 1px solid rgba(156, 163, 175, 0.3);
}

.market-status-badge--loading,
.market-status-badge--error {
  cursor: pointer;
}

.market-status-badge--error:hover {
  opacity: 0.8;
}

/* Compact mode */
.market-status-badge.market-status-badge--compact {
  padding: 4px 8px;
  gap: 4px;
}
```

---

### Step 5: Modify GlobalHeader

**File**: `frontend/src/components/GlobalHeader.tsx`

**Add at the top**:
```typescript
import MarketStatusBadge from './MarketStatusBadge'
```

**Modify the right section** (around line 337):
```typescript
{/* Status Indicators */}
<div className="global-header__right">
  {/* Add Market Status Badge */}
  <MarketStatusBadge calendar="NSE" showHours={true} />

  {symbol && (
    <div className="global-header__status">Symbol: {symbol}</div>
  )}
  {/* ... rest of status indicators ... */}
</div>
```

---

### Step 6: Configure Environment Variables

**File**: `frontend/.env` (or `.env.local`)

```bash
# Calendar Service API URL
VITE_CALENDAR_BASE_URL=http://localhost:8081/calendar

# Or for production
# VITE_CALENDAR_BASE_URL=/calendar
```

---

### Step 7: Optional - Holiday Calendar Widget

**File**: `frontend/src/components/HolidayCalendar.tsx`

```typescript
import React, { useState, useEffect } from 'react'
import { Holiday } from '../types/calendar'
import { getHolidays, formatDate, getDaysUntil } from '../services/calendarApi'
import './HolidayCalendar.css'

interface HolidayCalendarProps {
  calendar?: string
  limit?: number
}

const HolidayCalendar: React.FC<HolidayCalendarProps> = ({
  calendar = 'NSE',
  limit = 5
}) => {
  const [holidays, setHolidays] = useState<Holiday[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    const fetchHolidays = async () => {
      try {
        const currentYear = new Date().getFullYear()
        const data = await getHolidays(calendar, currentYear)

        // Filter upcoming holidays
        const today = new Date().toISOString().split('T')[0]
        const upcoming = data
          .filter(h => h.date >= today)
          .slice(0, limit)

        setHolidays(upcoming)
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to load holidays'))
      } finally {
        setLoading(false)
      }
    }

    fetchHolidays()
  }, [calendar, limit])

  if (loading) {
    return (
      <div className="holiday-calendar">
        <div className="holiday-calendar__header">Upcoming Holidays</div>
        <div className="holiday-calendar__loading">Loading...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="holiday-calendar">
        <div className="holiday-calendar__header">Upcoming Holidays</div>
        <div className="holiday-calendar__error">Failed to load holidays</div>
      </div>
    )
  }

  if (holidays.length === 0) {
    return (
      <div className="holiday-calendar">
        <div className="holiday-calendar__header">Upcoming Holidays</div>
        <div className="holiday-calendar__empty">No upcoming holidays</div>
      </div>
    )
  }

  return (
    <div className="holiday-calendar">
      <div className="holiday-calendar__header">Upcoming Holidays</div>
      <div className="holiday-calendar__list">
        {holidays.map((holiday, index) => {
          const daysUntil = getDaysUntil(holiday.date)
          const isToday = daysUntil === 0
          const isTomorrow = daysUntil === 1

          return (
            <div key={index} className="holiday-calendar__item">
              <div className="holiday-calendar__icon">📅</div>
              <div className="holiday-calendar__info">
                <div className="holiday-calendar__name">{holiday.name}</div>
                <div className="holiday-calendar__date">
                  {formatDate(holiday.date)}
                  {isToday && <span className="holiday-calendar__badge">Today</span>}
                  {isTomorrow && <span className="holiday-calendar__badge">Tomorrow</span>}
                  {!isToday && !isTomorrow && daysUntil <= 7 && (
                    <span className="holiday-calendar__badge">in {daysUntil} days</span>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default HolidayCalendar
```

**File**: `frontend/src/components/HolidayCalendar.css`

```css
.holiday-calendar {
  background: var(--bg-secondary, #1e1e1e);
  border-radius: 8px;
  padding: 16px;
  min-width: 300px;
}

.holiday-calendar__header {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-primary, #e0e0e0);
}

.holiday-calendar__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.holiday-calendar__item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px;
  border-radius: 6px;
  background: var(--bg-tertiary, #2a2a2a);
  transition: background 0.2s ease;
}

.holiday-calendar__item:hover {
  background: var(--bg-hover, #333);
}

.holiday-calendar__icon {
  font-size: 24px;
  line-height: 1;
}

.holiday-calendar__info {
  flex: 1;
}

.holiday-calendar__name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary, #e0e0e0);
  margin-bottom: 4px;
}

.holiday-calendar__date {
  font-size: 12px;
  color: var(--text-secondary, #9ca3af);
  display: flex;
  align-items: center;
  gap: 8px;
}

.holiday-calendar__badge {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
}

.holiday-calendar__loading,
.holiday-calendar__error,
.holiday-calendar__empty {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary, #9ca3af);
  font-size: 14px;
}

.holiday-calendar__error {
  color: #ef4444;
}
```

---

## 🚀 Quick Start

### Minimal Integration (5 minutes)

If you just want the market status badge in the header:

1. **Copy 3 files**:
   - `types/calendar.ts`
   - `services/calendarApi.ts`
   - `hooks/useMarketStatus.ts`

2. **Add to .env**:
   ```bash
   VITE_CALENDAR_BASE_URL=http://localhost:8081/calendar
   ```

3. **Use inline in GlobalHeader**:
   ```typescript
   import { useMarketStatus } from '../hooks/useMarketStatus'

   // Inside GlobalHeader component
   const { display } = useMarketStatus({ calendar: 'NSE' })

   // In render
   <div className={`global-header__status global-header__status--${display.color}`}>
     {display.icon} {display.label}
   </div>
   ```

---

## 🧪 Testing

### 1. Test API Connection

```typescript
// In browser console
import { getMarketStatus } from './services/calendarApi'

const status = await getMarketStatus('NSE')
console.log(status)
```

### 2. Test Component

Create a test page:

```typescript
// src/pages/CalendarTest.tsx
import React from 'react'
import MarketStatusBadge from '../components/MarketStatusBadge'
import HolidayCalendar from '../components/HolidayCalendar'

export default function CalendarTest() {
  return (
    <div style={{ padding: '24px', display: 'flex', gap: '24px' }}>
      <div>
        <h2>Market Status Badge</h2>
        <MarketStatusBadge calendar="NSE" showHours={true} />
      </div>

      <div>
        <h2>Holiday Calendar</h2>
        <HolidayCalendar calendar="NSE" limit={5} />
      </div>
    </div>
  )
}
```

### 3. Manual Test Checklist

✅ Market badge shows correct status
✅ Badge updates automatically (wait 1 minute)
✅ Tooltip shows on hover
✅ Special sessions display correctly (test with Muhurat trading date)
✅ Holiday calendar shows upcoming events
✅ Error states handled gracefully

---

## 🎨 Customization

### Change Colors

Edit `MarketStatusBadge.css`:

```css
.market-status-badge--green {
  background-color: rgba(34, 197, 94, 0.15);
  color: #22c55e;
  /* Your custom styles */
}
```

### Change Refresh Interval

```typescript
<MarketStatusBadge
  calendar="NSE"
  refreshInterval={30000}  // 30 seconds
/>
```

### Add Notification on Special Sessions

```typescript
const { status, display } = useMarketStatus({ calendar: 'NSE' })

useEffect(() => {
  if (status?.is_special_session && status.special_event_name) {
    // Show notification
    alert(`Special Session: ${status.special_event_name}`)
  }
}, [status?.is_special_session])
```

---

## 🔌 Advanced Integration

### WebSocket Updates (Future)

Currently, the hook uses polling (60-second refresh). For real-time updates:

```typescript
// Future: WebSocket integration
import { useEffect } from 'react'

export function useMarketStatusWebSocket(calendar: string) {
  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8081/calendar/ws')

    ws.onmessage = (event) => {
      const status = JSON.parse(event.data)
      // Update state
    }

    return () => ws.close()
  }, [calendar])
}
```

### Multiple Calendars

```typescript
// Monitor multiple markets
const nseStatus = useMarketStatus({ calendar: 'NSE' })
const bseStatus = useMarketStatus({ calendar: 'BSE' })
const mcxStatus = useMarketStatus({ calendar: 'MCX' })

return (
  <>
    <MarketStatusBadge calendar="NSE" compact />
    <MarketStatusBadge calendar="BSE" compact />
    <MarketStatusBadge calendar="MCX" compact />
  </>
)
```

---

## 📊 Performance Considerations

### Caching

The calendar service has built-in caching (5-min TTL), but you can add frontend caching:

```typescript
// Use React Query for better caching
import { useQuery } from '@tanstack/react-query'
import { getMarketStatus } from '../services/calendarApi'

export function useMarketStatus(calendar: string) {
  return useQuery({
    queryKey: ['marketStatus', calendar],
    queryFn: () => getMarketStatus(calendar),
    refetchInterval: 60000, // 1 minute
    staleTime: 30000 // Consider fresh for 30 seconds
  })
}
```

### Lazy Loading

```typescript
// Only load holiday calendar when needed
const HolidayCalendar = lazy(() => import('./HolidayCalendar'))

<Suspense fallback={<div>Loading...</div>}>
  <HolidayCalendar />
</Suspense>
```

---

## 🐛 Troubleshooting

### Issue: "Network Error"

**Solution**: Check CORS configuration in backend:

```python
# backend/app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Issue: Badge Not Updating

**Solution**: Check refreshInterval and browser console for errors:

```typescript
const { display, error } = useMarketStatus({
  calendar: 'NSE',
  refreshInterval: 60000
})

console.log('Error:', error)  // Check for errors
```

### Issue: Special Sessions Not Showing

**Solution**: Verify special session exists in database:

```bash
curl "http://localhost:8081/calendar/status?calendar=NSE&check_date=2026-11-01"
```

---

## 📚 Summary

### What You Built

✅ **TypeScript types** for type safety
✅ **API service** for calendar endpoints
✅ **React hook** for market status with auto-refresh
✅ **Market badge component** with color coding
✅ **Holiday calendar widget** (optional)
✅ **Integration** with GlobalHeader

### Time Investment

| Task | Time |
|------|------|
| Copy types & API service | 10 min |
| Create hook | 15 min |
| Create badge component | 20 min |
| Integrate with header | 10 min |
| Testing | 15 min |
| **Total (minimal)** | **~1 hour** |

### Next Steps

1. ✅ Test in development
2. ✅ Add to production build
3. ✅ Monitor performance
4. ⏭️ Add notifications for special sessions
5. ⏭️ Build admin UI (use Admin API)

---

**Version**: 1.0
**Last Updated**: November 1, 2025
**Status**: ✅ Ready for Integration
