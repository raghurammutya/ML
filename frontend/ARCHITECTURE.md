# MonitorV2 Architecture

## Component Hierarchy

```
MonitorV2 (Page Component)
│
├─ GlobalHeader
│  ├─ Logo
│  ├─ Universe Tabs
│  │  ├─ NIFTY (active)
│  │  ├─ BANKNIFTY
│  │  ├─ FINNIFTY
│  │  └─ [+] Add Universe
│  ├─ Trading Accounts
│  │  ├─ Live (🟢 active)
│  │  └─ Paper (🟠 inactive)
│  └─ User Menu
│     ├─ Profile
│     ├─ Settings
│     ├─ Theme Toggle
│     └─ Logout
│
├─ ControlPanel
│  ├─ Timeframe Selector
│  │  └─ [1min|5min|15min|30min|1hour|1day]
│  ├─ Indicator Selector (multi-select)
│  ├─ Expiry Filter (multi-select)
│  ├─ Replay Toggle
│  │  └─ (when enabled)
│  │     ├─ Play/Pause
│  │     ├─ Timeline Scrubber
│  │     ├─ Time Display
│  │     └─ Speed Selector
│  └─ Layout Actions
│     ├─ Save Layout
│     └─ Load Layout
│
└─ UniversePage (Main Layout)
   │
   ├─ LEFT COLUMN (280px)
   │  │
   │  ├─ MetricPanelLeft (height: 500px)
   │  │  ├─ Header (indicator name, legend toggle)
   │  │  └─ Chart Area (synced Y-axis)
   │  │
   │  └─ RadarChartLeft (height: 300px)
   │     ├─ Header
   │     └─ Radar Chart Area
   │
   ├─ CENTER COLUMN (flex-1)
   │  │
   │  ├─ UnderlyingChart (height: 500px)
   │  │  ├─ Header (symbol, timeframe, controls)
   │  │  │  ├─ Candle Type Toggle
   │  │  │  ├─ Volume Toggle
   │  │  │  └─ Grid Toggle
   │  │  └─ Chart Area
   │  │
   │  └─ MetricTabs (height: 300px)
   │     ├─ Tab Headers
   │     │  ├─ Theta (🔴)
   │     │  ├─ Gamma (🟠)
   │     │  ├─ Delta (🟢)
   │     │  ├─ IV (🔵)
   │     │  ├─ Vega (🟣)
   │     │  └─ OI (🌸)
   │     └─ Tab Content (synced X-axis)
   │
   └─ RIGHT COLUMN (280px)
      │
      ├─ MetricPanelRight (height: 500px)
      │  ├─ Header (indicator selector)
      │  └─ Chart Area (synced Y-axis)
      │
      └─ RadarChartRight (height: 300px)
         ├─ Header
         └─ Radar Chart Area
```

---

## Layout Dimensions

```
┌──────────────────────────────────────────────────────────────────┐
│                         GlobalHeader (56px)                       │
│  Logo | [NIFTY] [BankNIFTY] [+]  | [Live] [Paper] | (User) ☰    │
└──────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────┐
│                       ControlPanel (~80px)                        │
│  TF: [5min] | Indicators: [IV,Delta...] | Expiry: [...] | ⏯     │
└──────────────────────────────────────────────────────────────────┘
┌─────────────┬──────────────────────────────────┬────────────────┐
│ Left Panel  │      Center Panel (flex-1)       │  Right Panel   │
│  (280px)    │                                  │    (280px)     │
│             │                                  │                │
│┌───────────┐│┌────────────────────────────────┐│┌──────────────┐│
││           │││    UnderlyingChart (500px)     │││              ││
││  Metric   │││  ┌────────────────────────┐   │││   Metric     ││
││  Panel    │││  │   NIFTY 5min           │   │││  Distribution││
││  Left     │││  │                        │   │││              ││
││  (500px)  │││  │   [📊 Placeholder]     │   │││   (500px)    ││
││           │││  │                        │   │││              ││
││  (Y-axis  │││  └────────────────────────┘   │││  (Y-axis     ││
││   synced) │││                                │││   synced)    ││
│└───────────┘│└────────────────────────────────┘│└──────────────┘│
│             │                                  │                │
│┌───────────┐│┌────────────────────────────────┐│┌──────────────┐│
││  Radar    │││    MetricTabs (300px)          │││   Radar      ││
││  Chart    │││  [Theta|Gamma|Delta|IV|Vega|OI]│││   Chart      ││
││  Left     │││  ┌────────────────────────┐   │││   Right      ││
││  (300px)  │││  │                        │   │││   (300px)    ││
││           │││  │   [📊 Placeholder]     │   │││              ││
│└───────────┘│└────────────────────────────────┘│└──────────────┘│
└─────────────┴──────────────────────────────────┴────────────────┘
```

Total Height: ~950px (without padding/gaps)
Total Width: 100vw (responsive)

---

## State Flow

```
MonitorV2 (Top-level State)
│
├─ theme: ThemeMode
├─ selectedAccountId: string
├─ activeUniverse: Universe
├─ timeframe: Timeframe
│
├─ currentLayout: UniverseLayout
│  ├─ showLeftPanel: boolean
│  ├─ showRightPanel: boolean
│  ├─ showRadarCharts: boolean
│  ├─ panelWidths: number
│  └─ panelHeights: number
│
├─ filters: UniverseFilters
│  ├─ selectedExpiries: string[]
│  ├─ indicators: IndicatorType[]
│  └─ strikeRange: number
│
├─ chartConfig: ChartConfig
│  ├─ symbol: string
│  ├─ timeframe: Timeframe
│  ├─ candleType: 'candle' | 'line' | 'area'
│  ├─ showVolume: boolean
│  └─ showGrid: boolean
│
├─ replayState: ReplayState
│  ├─ enabled: boolean
│  ├─ currentTime: number
│  ├─ playbackSpeed: number
│  └─ isPlaying: boolean
│
└─ savedLayouts: UniverseLayout[]
   └─ [layout1, layout2, ...]
```

**Data Flow Direction:**
```
MonitorV2 → GlobalHeader (props)
         → ControlPanel (props)
         → UniversePage (props)
            → UnderlyingChart (props)
            → MetricPanelLeft (props)
            → MetricPanelRight (props)
            → MetricTabs (props)
            → RadarCharts (props)
```

**Event Flow Direction:**
```
User Interaction → Component Handler → Parent setState → Re-render
```

---

## Data Models

### Chart Data
```tsx
interface OHLCBar {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}
```

### Strike Data
```tsx
interface StrikeData {
  strike: number
  expiry: string
  callIV: number       // CALL side IV
  putIV: number        // PUT side IV
  callDelta: number
  putDelta: number
  callGamma: number
  putGamma: number
  callTheta: number
  putTheta: number
  callVega: number
  putVega: number
  callOI: number
  putOI: number
  callVolume: number
  putVolume: number
  underlying: number
}
```

### Metric Series
```tsx
interface MetricSeries {
  expiry: string       // e.g., "2025-11-04"
  data: StrikeData[]   // Array of strikes
  color: string        // For chart rendering
}
```

---

## API Integration Points (Phase 2)

### Endpoints Needed

1. **Underlying Price Data**
   - Endpoint: `/history`
   - Returns: `OHLCBar[]`
   - Update: Real-time (WebSocket or 1s polling)

2. **Strike Distribution**
   - Endpoint: `/fo/strike-distribution`
   - Returns: `MetricSeries[]`
   - Update: Every 5 seconds
   - Used by: MetricPanelLeft, MetricPanelRight

3. **Moneyness Series**
   - Endpoint: `/fo/moneyness-series`
   - Returns: `MoneynessData[]`
   - Update: Every 5 seconds
   - Used by: MetricTabs

4. **Available Expiries**
   - Endpoint: `/fo/expiries`
   - Returns: `string[]`
   - Update: Once per day

5. **Indicator Definitions**
   - Endpoint: `/fo/indicators`
   - Returns: `MetricTabConfig[]`
   - Update: On page load

6. **Real-time Updates**
   - Endpoint: `/fo/stream` (WebSocket)
   - Pushes: Strike updates
   - Frequency: Every 5 seconds

---

## Chart Synchronization

### Y-Axis Synchronization (Vertical)
```
UnderlyingChart (master)
    ↓ (priceRange: {min, max})
MetricPanelLeft (slave) ←── Synced
MetricPanelRight (slave) ←─ Synced

Mechanism:
- UnderlyingChart calculates visible price range
- Passes range to side panels via props
- Side panels use same Y-axis domain
```

### X-Axis Synchronization (Horizontal)
```
UnderlyingChart (master)
    ↓ (timeRange: {from, to})
MetricTabs (slave) ←── Synced

Mechanism:
- UnderlyingChart controls visible time range
- Passes range to bottom tabs
- Tabs filter data to same time window
```

---

## Responsive Breakpoints (Future)

```css
/* Desktop (default) */
min-width: 1280px
├─ Left: 280px
├─ Center: flex-1
└─ Right: 280px

/* Laptop */
max-width: 1280px
├─ Left: 220px
├─ Center: flex-1
└─ Right: 220px

/* Tablet */
max-width: 1024px
├─ Left: hidden (collapsible)
├─ Center: 100%
└─ Right: hidden (collapsible)

/* Mobile */
max-width: 768px
├─ Stack all panels vertically
└─ Full-width components
```

---

## Theme System (Future)

```tsx
// Light Theme
background: #ffffff
panels: #f3f4f6
borders: #e5e7eb
text: #111827

// Dark Theme (Current)
background: #030712
panels: #111827
borders: #374151
text: #ffffff

// Auto Theme
Uses system preference (prefers-color-scheme)
```

---

## Performance Considerations

### Current (Phase 1)
- **No data fetching** - Instant load
- **No re-renders** - Static mock data
- **Bundle size** - ~50KB (uncompressed)

### Future (Phase 2+)
- **Data caching** - Redis + LocalStorage
- **Lazy loading** - Code splitting by route
- **Virtualization** - For large data sets (100+ strikes)
- **Debouncing** - Filter changes (300ms delay)
- **Memoization** - React.memo for expensive components
- **WebWorkers** - Heavy calculations off main thread

---

## Testing Strategy (Future Phases)

### Unit Tests
- Component rendering
- Event handlers
- State updates
- Props validation

### Integration Tests
- API integration
- WebSocket connection
- Layout persistence
- Replay mode

### E2E Tests
- User workflows
- Multi-universe switching
- Layout save/load
- Replay playback

---

**Architecture Status:** ✅ COMPLETE (Phase 1)
**Last Updated:** 2025-11-02
