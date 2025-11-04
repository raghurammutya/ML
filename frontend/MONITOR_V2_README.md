# MonitorV2 - Trading Analytics Dashboard

**Phase 1: Layout & Structure** ✅ COMPLETE

A complete rewrite of the trading monitor interface with modern architecture, TypeScript, and modular design.

---

## 📁 File Structure

```
src/
├── types/
│   └── monitor-v2.ts                 # All TypeScript interfaces
├── components/
│   └── monitor-v2/
│       ├── index.ts                  # Barrel export
│       ├── GlobalHeader.tsx          # Sticky top header
│       ├── ControlPanel.tsx          # Filters & controls
│       ├── UniversePage.tsx          # Main layout container
│       ├── UnderlyingChart.tsx       # Central chart area
│       ├── MetricPanelLeft.tsx       # Left sidebar panel
│       ├── MetricPanelRight.tsx      # Right sidebar panel
│       ├── MetricTabs.tsx            # Bottom tabs (Theta, Gamma, etc.)
│       ├── RadarChartLeft.tsx        # Optional radar chart (left)
│       └── RadarChartRight.tsx       # Optional radar chart (right)
└── pages/
    └── MonitorV2.tsx                 # Main page component
```

---

## 🎨 Features Implemented (Phase 1)

### ✅ Global Header
- **User Dropdown**: Profile, Settings, Theme Toggle, Logout
- **Trading Accounts**: Pill-style buttons (Live, Paper, Backtest)
- **Universe Tabs**: NIFTY, BankNIFTY, etc. with "+" to add custom underlyings
- **Sticky positioning**: Always visible at top

### ✅ Control Panel
- **Timeframe Selector**: 1min, 5min, 15min, 30min, 1hour, 1day
- **Indicator Selector**: Multi-select for IV, Delta, Gamma, Theta, Vega, OI, PCR
- **Expiry Filter**: Multi-select dropdown
- **Replay Mode Toggle**: Enable/disable with playback controls
- **Layout Actions**: Save/Load custom layouts

### ✅ Main Layout (UniversePage)
- **3-Column Responsive Grid**:
  - Left Panel (280px) - Metric charts synced with Y-axis
  - Center Panel (flex-1) - Underlying chart + bottom tabs
  - Right Panel (280px) - Distribution charts synced with Y-axis

- **Center Column**:
  - Underlying Chart (500px height)
  - Metric Tabs (300px height) - Theta, Gamma, Delta, IV, Vega, OI

- **Optional Radar Charts**: Multi-dimensional metric views

### ✅ TypeScript Interfaces
All data models defined in `types/monitor-v2.ts`:
- `UniverseLayout` - Layout configuration
- `ReplayState` - Replay mode state
- `ChartConfig` - Chart display settings
- `UniverseFilters` - Filter selections
- `MetricTabConfig` - Bottom tab configuration
- `SidePanelConfig` - Left/right panel settings
- `AccountPanelState` - Trading account state
- `Strategy`, `Position`, `Order` - Trading models
- `StrikeData`, `MoneynessData` - Options data
- And more...

---

## 🚀 Usage

### Access the Page

Add route in `src/App.tsx`:
```tsx
import MonitorV2 from './pages/MonitorV2'

// In your routes:
<Route path="/monitor-v2" element={<MonitorV2 />} />
```

Navigate to: **http://localhost:3001/monitor-v2**

### Mock Data

All components use placeholder mock data in Phase 1:
- Empty chart data arrays
- Mock trading accounts
- Mock expiries
- Placeholder radar data

---

## 🎯 Design Principles

### 1. **Modular Components**
Each component is self-contained with clear props interfaces:
```tsx
interface MetricPanelProps {
  position: 'left' | 'right'
  config: SidePanelConfig
  series: MetricSeries[]
  priceRange: { min: number; max: number }
  onConfigChange: (config: Partial<SidePanelConfig>) => void
  height: number
}
```

### 2. **Type Safety**
Full TypeScript coverage with no `any` types. All interfaces exported from `types/monitor-v2.ts`.

### 3. **Responsive Layout**
- Flexbox-based grid system
- Configurable panel widths/heights
- Maintains aspect ratios

### 4. **State Management**
- Local state in `MonitorV2.tsx` for global settings
- Component-specific state in each component
- Props for communication

### 5. **Tailwind CSS Styling**
- Dark theme by default
- Consistent color palette (gray-900, blue-600, etc.)
- Hover states and transitions

---

## 🧩 Component Details

### GlobalHeader
**Props**: `GlobalHeaderProps`
- User profile dropdown with avatar
- Trading account switcher (live/paper/backtest indicators)
- Universe tabs with active state
- Theme selector (light/dark/auto)

**State**: `showUserMenu` (local)

### ControlPanel
**Props**: `ControlPanelProps`
- Timeframe selector (horizontal button group)
- Multi-select indicators and expiries
- Replay mode with timeline scrubber
- Save/Load layout actions

**Replay Controls** (shown when enabled):
- Play/Pause button
- Timeline slider
- Current time display
- Playback speed selector (1x, 2x, 5x, 10x)

### UniversePage
**Props**: Layout config, filters, chart config, replay time
- Manages 3-column grid layout
- Conditionally renders left/right panels
- Passes synchronized price ranges to side panels
- Manages bottom tabs state

**Local State**:
- `leftPanelConfig`, `rightPanelConfig`
- `metricTabs` array with active states
- `activeTabId`

### UnderlyingChart
**Props**: Symbol, timeframe, data, config, height
- Chart header with symbol and timeframe
- Candle type toggles (candlestick/line/area)
- Volume and grid toggles
- Placeholder for chart library integration

### MetricPanelLeft / MetricPanelRight
**Props**: Position, config, series, price range, height
- Panel header with indicator name
- Indicator selector (right panel only)
- Legend toggle
- Y-axis synced with main chart
- Placeholder for Recharts/D3 integration

### MetricTabs
**Props**: Tabs config, active tab, series, height, expiries
- Horizontal tab headers with color indicators
- Active tab highlighting
- X-axis synced with main chart
- Supports reordering via `order` field

### RadarChartLeft / RadarChartRight
**Props**: Position, data, height
- Multi-dimensional metric visualization
- Placeholder for radar chart library

---

## 🔧 Configuration

### Layout Configuration
```tsx
const layout: UniverseLayout = {
  id: 'default',
  name: 'Default Layout',
  universe: 'NIFTY',
  showLeftPanel: true,          // Toggle left panel
  showRightPanel: true,         // Toggle right panel
  showRadarCharts: true,        // Toggle radar charts
  leftPanelWidth: 280,          // px
  rightPanelWidth: 280,         // px
  chartHeight: 500,             // px
  bottomTabsHeight: 300,        // px
  activeTabs: ['theta', 'gamma', 'delta', 'iv', 'vega', 'oi'],
  savedAt: Date.now(),
}
```

### Chart Configuration
```tsx
const chartConfig: ChartConfig = {
  symbol: 'NIFTY',
  timeframe: '5min',
  showVolume: true,
  showGrid: true,
  candleType: 'candle',         // 'candle' | 'line' | 'area'
  theme: 'dark',
  timezone: 'Asia/Kolkata',
  autoScale: true,
}
```

### Filters
```tsx
const filters: UniverseFilters = {
  selectedExpiries: ['2025-11-04', '2025-11-11', '2025-11-18'],
  availableExpiries: MOCK_EXPIRIES,
  strikeRange: 10,              // ATM ± 10 strikes
  indicators: ['iv', 'delta', 'gamma', 'theta', 'vega', 'oi'],
  optionSide: 'both',           // 'call' | 'put' | 'both'
  minOI: 0,
  minVolume: 0,
}
```

---

## 📊 Data Flow (Placeholder)

```
MonitorV2 (Page)
    ↓ (state)
GlobalHeader ← User, Accounts, Universes
ControlPanel ← Filters, Timeframe, Replay
UniversePage ← Layout, Filters, ChartConfig
    ↓ (renders)
├─ MetricPanelLeft
│   └─ (synced Y-axis)
├─ UnderlyingChart
│   └─ (main price axis)
├─ MetricPanelRight
│   └─ (synced Y-axis)
└─ MetricTabs
    └─ (synced X-axis)
```

---

## 🎨 Color Palette

```css
/* Dark Theme (Default) */
Background:     #030712 (gray-950)
Panels:         #111827 (gray-900)
Borders:        #374151 (gray-700)
Headers:        #1f2937 (gray-800)
Text:           #ffffff (white)
Text Secondary: #9ca3af (gray-400)
Active:         #2563eb (blue-600)
Success:        #10b981 (green-600)
Warning:        #f59e0b (amber-500)
Error:          #ef4444 (red-500)

/* Metric Colors */
Theta:  #ef4444 (red-500)
Gamma:  #f59e0b (amber-500)
Delta:  #10b981 (green-500)
IV:     #3b82f6 (blue-500)
Vega:   #8b5cf6 (purple-500)
OI:     #ec4899 (pink-500)
```

---

## 🚦 Next Steps (Phase 2+)

### Phase 2: Data Integration
- [ ] Connect to backend API endpoints
- [ ] Implement real-time WebSocket for chart data
- [ ] Fetch strike distribution data
- [ ] Implement data caching strategy

### Phase 3: Chart Libraries
- [ ] Integrate TradingView Lightweight Charts
- [ ] Add Recharts for metric panels
- [ ] Implement D3 for radar charts
- [ ] Add technical indicators overlay

### Phase 4: Replay Mode
- [ ] Implement timeline scrubber with data fetching
- [ ] Add playback controls (play/pause/speed)
- [ ] Support frame-by-frame navigation
- [ ] Save/load replay sessions

### Phase 5: Layout Persistence
- [ ] Save layouts to LocalStorage
- [ ] Export/import layouts as JSON
- [ ] Sync layouts across devices (backend)
- [ ] Layout templates library

### Phase 6: Advanced Features
- [ ] Alert creation from panels (right-click menu)
- [ ] Strategy builder UI
- [ ] Position management panel
- [ ] Order execution integration
- [ ] Multi-universe comparison view

---

## 🐛 Known Limitations (Phase 1)

- **No real data**: All components use mock/placeholder data
- **No charts**: Chart areas show placeholders only
- **No persistence**: Layouts not saved to storage
- **No API calls**: No backend integration
- **No error handling**: No loading states or error boundaries
- **No responsive breakpoints**: Fixed panel widths
- **No accessibility**: No ARIA labels or keyboard navigation

These will be addressed in future phases.

---

## 📝 Developer Notes

### Adding New Metrics

1. Add to `IndicatorType` in `types/monitor-v2.ts`:
```tsx
export type IndicatorType = 'iv' | 'delta' | 'gamma' | 'theta' | 'vega' | 'volume' | 'oi' | 'pcr' | 'rho'
```

2. Add to `INDICATORS` array in `ControlPanel.tsx`

3. Add to default `metricTabs` in `UniversePage.tsx`

### Customizing Layout

Modify `currentLayout` state in `MonitorV2.tsx`:
```tsx
const [currentLayout, setCurrentLayout] = useState<UniverseLayout>({
  // ... custom settings
  showLeftPanel: false,  // Hide left panel
  chartHeight: 600,      // Taller chart
})
```

### Styling

All components use Tailwind CSS classes. To customize:
- Modify className strings in component JSX
- Add custom CSS to `index.css` if needed
- Use Tailwind config for theme customization

---

## 🤝 Contributing

When adding features:
1. Define types in `types/monitor-v2.ts` first
2. Create modular components with clear props
3. Use TypeScript strictly (no `any`)
4. Follow existing naming conventions
5. Add comments for complex logic
6. Update this README with changes

---

## 📚 References

- **TypeScript**: Strict mode, no implicit any
- **React**: Functional components with hooks
- **Tailwind CSS**: Utility-first styling
- **State Management**: React useState (will add Context/Redux later)

---

**Phase 1 Status**: ✅ COMPLETE
**Last Updated**: 2025-11-02
**Author**: AI Code Analysis
