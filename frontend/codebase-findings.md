# Codebase Findings for Future Sprints

## Code Study Summary

### Frontend Files Found
- **frontend/src/pages/MonitorPage.tsx** - Main derivatives monitor page with chart and panels
- **frontend/src/components/CustomChartWithMLLabels.tsx** - Standalone chart with full label CRUD and context menu
- **frontend/src/components/nifty-monitor/UnderlyingChart.tsx** - Basic chart used in MonitorPage (no labels)
- **frontend/src/services/api.ts** - Base API client using axios
- **frontend/src/services/fo.ts** - F&O service with WebSocket patterns
- **frontend/src/services/monitor.ts** - Monitor service with WebSocket patterns
- **frontend/src/types.ts** - TypeScript type definitions

### Backend Files Found
- **backend/app/routes/labels.py** - Existing label CRUD endpoints (POST/DELETE)
- **backend/app/routes/fo.py** - F&O WebSocket stream implementation
- **backend/app/routes/nifty_monitor.py** - Monitor WebSocket stream
- **backend/app/realtime.py** - RealTimeHub pub/sub implementation
- **backend/app/main.py** - FastAPI app initialization
- **backend/app/config.py** - Configuration with defaults
- **backend/app/database.py** - Asyncpg connection pool

### Database Structure
- **Table: ml_labeled_data** - Current label storage (includes OHLC data)
- **TimescaleDB** - Used for time-series with hypertables and continuous aggregates
- **No dedicated migrations directory** - Uses direct SQL/asyncpg

### Key Technology Stack
- **Frontend**: React, TypeScript, TradingView Lightweight Charts, Vite
- **Backend**: FastAPI, asyncpg, Redis, TimescaleDB
- **WebSocket**: Native WebSocket API (frontend), FastAPI WebSocket (backend)
- **Patterns**: RealTimeHub for pub/sub, service-based architecture

## Important Notes for Implementation

### Context Menu Implementation
CustomChartWithMLLabels.tsx already has a complete context menu implementation:
- Right-click capture with timestamp snapping
- React Portal for rendering outside component
- Position calculation and outside-click handling
- Integration with label CRUD operations

### WebSocket Patterns
Both FO and Monitor services follow consistent patterns:
- Build WebSocket URL from API base URL
- Handle heartbeat/ping for connection health
- Queue-based message distribution via RealTimeHub
- Graceful shutdown and reconnection logic

### Label Data Model Changes Needed
Current ml_labeled_data stores full OHLC data. Sprint 1 requires metadata-only model:
- Need new table structure with metadata JSONB
- Metadata must include: timeframe, nearest_candle_timestamp_utc, sample_offset_seconds
- Remove OHLC storage from labels table

### Default Configuration Values
- Max strikes per expiry: 50
- Strike gap: 50
- Max moneyness level: 10
- WebSocket timeout: 30 seconds
- Database query timeout: 30 seconds

### Missing Infrastructure
- No formal database migrations system
- Need to add ml_labels and ml_label_samples tables
- Need to add label WebSocket channel to RealTimeHub
- Need to create frontend/src/services/labels.ts

## Recommendations for Sprint 1

1. **Reuse context menu logic** from CustomChartWithMLLabels.tsx
2. **Follow WebSocket patterns** from fo.ts and nifty_monitor.py
3. **Create proper migrations** for new table structure
4. **Use existing RealTimeHub** for label broadcasts
5. **Maintain consistent service architecture** in frontend

---

## Sprint 1 Implementation (Completed)

### New Database Tables
- **backend/migrations/001_create_ml_labels.sql** - Created ml_labels table with metadata-only storage
  - Columns: id, symbol, label_type, timeframe, nearest_candle_timestamp_utc, sample_offset_seconds, price, tags
  - Foreign key to ml_label_samples table (not yet implemented)
  - Indexes on symbol, label_type, and timestamp for efficient queries

### Backend Changes
- **backend/app/routes/labels.py** - Enhanced label CRUD endpoints
  - POST /labels/ml - Create label with metadata validation
  - DELETE /labels/ml/:id - Delete label by ID
  - GET /labels/ml - List labels with filtering
  - Metadata stored as JSONB for flexibility

- **backend/app/routes/label_stream.py** - WebSocket stream for label updates
  - Real-time label broadcasts via RealTimeHub
  - Fixed subscription pattern: `client_queue = await labels_hub.subscribe()`
  - Message format: `{"type": "label_created"|"label_deleted", "data": {...}}`

### Frontend Changes
- **frontend/src/services/labels.ts** - New label service
  - createLabel(), deleteLabel(), getLabels() API functions
  - WebSocket subscription with reconnection logic
  - TypeScript interfaces: Label, LabelMetadata, LabelType

- **frontend/src/types/labels.ts** - Label type definitions
  - LabelType: 'bullish' | 'bearish' | 'neutral'
  - LabelMetadata with timeframe, timestamp, offset, price fields

- **frontend/src/components/nifty-monitor/UnderlyingChart.tsx** - Context menu integration
  - Right-click context menu with "Set Bullish" / "Set Bearish" options
  - Label creation on candle timestamps
  - WebSocket subscription for real-time label updates
  - Visual label markers on chart

- **frontend/src/components/nifty-monitor/VerticalPanel.tsx** - Context menu added
  - Right-click menu: Copy value, Add Alert, Settings, Show Chart
  - Dark theme styling matching TradingView

- **frontend/src/components/nifty-monitor/HorizontalPanel.tsx** - Context menu added
  - Same context menu as VerticalPanel
  - Works even when panels are empty (no data dependency)

### Key Patterns Established
- Metadata-only storage (no OHLC in ml_labels)
- JSONB metadata for extensibility
- RealTimeHub for label broadcasts
- Context menu reuse across components
- IST timezone display throughout

---

## Sprint 2 Implementation (Completed)

### New Components
- **frontend/src/components/ShowChartPopup/DerivativesChartPopup.tsx** - Popup chart with pinning
  - TradingView Lightweight Charts integration
  - Multi-expiry selector with color-coded lines
  - Independent replay cursor with pin functionality
  - Greek metrics overlay (IV, Delta, Gamma, Theta, Vega)
  - Historical data fetch on mount
  - WebSocket subscription for live updates (1s cadence)

- **frontend/src/components/ShowChartPopup/ShowChartPopup.tsx** - Generic wrapper
  - Handles both underlying and derivatives popups
  - Modal with draggable header, resizable body
  - Close/pin controls

### Database Changes
- **backend/migrations/002_add_pinned_cursor_state.sql** - Pinned state support
  - Added pinnedCursorState JSONB column to ml_labels
  - Stores: timestamp, replay_mode flag
  - Allows restoring popup state from saved labels

### Backend Endpoints
- **backend/app/routes/historical.py** - New historical data endpoint
  - GET /historical/series - Fetch option candles and Greeks
  - Query params: underlying, strike, bucket, expiry, timeframe, start, end
  - Returns: timestamps[], candles[], metrics[] (IV, Delta, Gamma, Theta, Vega)
  - Queries fo_option_strike_bars aggregated table
  - Simulates OHLC from close price (no raw tick data stored)

### Backend WebSocket
- **backend/app/routes/fo.py** - Popup subscription handlers
  - subscribe_popup message type for popup-level subscriptions
  - popup_update message type for live data
  - Per-popup subscription management (independent of main stream)
  - 1s update cadence during market hours

### Frontend Integration
- **frontend/src/pages/MonitorPage.tsx** - Popup state management
  - showDerivativesPopup state with bucket/expiry/timestamp context
  - handlePopupPin creates ml_label with pinnedCursorState metadata
  - Opens popup from horizontal/vertical panel context menus

- **frontend/src/types/labels.ts** - Extended metadata
  - Added strike?: number, bucket?: string to LabelMetadata
  - Supports both underlying and derivative popup pinning

### Known Issues & Workarounds
- **Pre-existing bug in /fo/moneyness-series** (not Sprint 2 related)
  - DataManager missing methods: fetch_fo_strike_rows, fetch_fo_expiry_metrics
  - fo_option_strike_bars lacks OI columns (call_oi_sum, put_oi_sum)
  - Temporary fix: Returns empty series data to unblock UI testing
  - Horizontal panels load but show no data
  - Does not affect Sprint 2 popup functionality

### Technical Decisions
- Popup subscriptions are independent (not coupled to main monitor stream)
- Historical data fetched on-demand (not preloaded)
- Pin state persisted as label metadata (reusable pattern)
- Greek metrics from aggregated table (fo_option_strike_bars)
- Context menus work even on empty panels (no data dependency)

### Testing Checklist
- [x] Context menus appear on horizontal/vertical panels
- [x] "Show Chart" opens DerivativesChartPopup
- [x] Historical data loads in popup
- [x] Pin functionality persists to ml_labels
- [ ] Live WebSocket updates in popup (requires market hours)
- [ ] Horizontal panels display data (blocked by pre-existing OI bug)

---

## Sprint 3 Implementation (Completed - Foundation)

### New Components & Hooks
- **frontend/src/hooks/useReplayMode.ts** - Replay state management hook
  - Enter/exit replay mode with window fetching
  - Play/pause/step controls with configurable speeds (0.1x to 10x)
  - Seek to timestamp, rewind/fast forward actions
  - Buffered data management for local playback
  - Automatic cursor advancement with interval management

- **frontend/src/components/nifty-monitor/ReplayControls.tsx** - Playback controls UI
  - Time badge showing current cursor position in IST
  - Play/Pause/Step/Rewind/Fast Forward buttons
  - Speed selector with +/- controls
  - Exit button and "End of Data" indicator
  - Disabled states for boundary conditions

- **frontend/src/components/nifty-monitor/ReplayWatermark.tsx** - Replay mode indicator
  - Semi-transparent "REPLAY MODE" watermark overlay
  - Rotated text with shadow effects
  - Non-interactive, visual-only indicator

### Backend Replay System
- **backend/app/routes/replay.py** - Replay window endpoint
  - GET /replay/window - Fetch historical time-series window
  - Query params: underlying, timeframe, start, end, expiries, strikes, panels
  - Returns: timestamps[], candles[], panels{} with aligned series
  - Queries underlying_bars and fo_option_strike_bars tables
  - Supports Greek panels: iv, delta, gamma, theta, vega for calls/puts

- **backend/app/main.py** - Registered replay router
  - Replay endpoints available at /replay/*

### Type Definitions
- **frontend/src/types/replay.ts** - Complete replay type system
  - ReplayState: isActive, cursorUtc, playbackSpeed, bufferedData
  - ReplayControls: enter, exit, play, pause, step, seek, setSpeed
  - PerformanceMode: enabled, reducedCadence, disableSparklines
  - ReplayWindowRequest/Response: API contracts
  - ReplayFrameMessage, BackpressureMessage: WebSocket messages

### Services
- **frontend/src/services/replay.ts** - Replay data fetching
  - fetchReplayWindow() - HTTP bulk window fetch
  - ReplayWebSocketClient - Streaming replay frames (optional mode)
  - enterReplay/exitReplay WebSocket messages
  - Auto-reconnect on disconnect

### Styling
- **frontend/src/index.css** - Replay and performance mode styles
  - .replay-watermark - Large rotated semi-transparent overlay
  - .replay-cursor - Vertical line with glow effect
  - .future-data - De-emphasized (30% opacity, grayscale)
  - .replay-controls - Floating toolbar with dark theme
  - .perf-mode-toggle - Performance mode button styles
  - .perf-mode-badge - Warning badge for reduced cadence mode

### Key Features Implemented

**Replay Mode Architecture:**
- Page-level replay (not global) - each page can independently enter replay
- HTTP window fetch for 6-hour historical buffer
- Local playback engine with configurable speed multipliers
- Step-by-step candle navigation
- Cursor synchronization across all panels (main chart + horizontal + vertical)
- Future data de-emphasis (right-of-cursor at 30% opacity + grayscale)

**Performance Mode Foundation:**
- Type definitions for performance state
- UI styling for toggle and badge
- Backpressure message type for server-initiated cadence reduction
- Client acknowledgment pattern via WebSocket

**Default UX Constants:**
```typescript
DEFAULT_UX = {
  strikes: { window: 20 },        // ±20 from ATM
  expiries: { count: 3 },          // 3 nearest
  seriesPerPanel: { max: 3 },     // Max 3 lines
  layout: {
    mainChartHeight: '60vh',
    horizontalPanelHeight: '120px',
    verticalPanelWidth: '200px'
  }
}
```

### Integration Points

**To Complete Sprint 3:**
1. **MonitorPage Integration**:
   - Import useReplayMode hook
   - Add "Replay" button to header controls
   - Add "Performance Mode" toggle to header
   - Wrap chart area with ReplayWatermark when state.isActive
   - Render ReplayControls when state.isActive
   - Pass replay cursor to MonitorSyncContext for panel synchronization

2. **Panel Sync**:
   - Update UnderlyingChart to render vertical cursor at replayCursor position
   - Apply .future-data class to candles right of cursor
   - Update HorizontalPanel/VerticalPanel to sync crosshair with replay cursor
   - Disable live WebSocket subscriptions when replay active

3. **Performance Mode**:
   - Implement toggle handler in MonitorPage
   - Update subscription cadence from 1s to 5s when enabled
   - Show perf-mode-badge in header
   - Handle backpressure messages from server

4. **Grid Layout** (Future):
   - Install react-grid-layout: `npm install react-grid-layout`
   - Wrap horizontal/vertical panel stacks with GridLayout
   - Allow drag-and-drop reordering
   - Persist layout to localStorage or backend

### Database Requirements
- **underlying_bars** table must exist with columns:
  - symbol, timeframe, bucket_time, open, high, low, close, volume
- **fo_option_strike_bars** table must have:
  - symbol, timeframe, bucket_time, strike, expiry
  - call_iv_avg, put_iv_avg, call_delta_avg, put_delta_avg
  - call_gamma_avg, put_gamma_avg, call_theta_avg, put_theta_avg
  - call_vega_avg, put_vega_avg

### Testing Checklist (Sprint 3)
- [ ] Replay button triggers window fetch and enters replay mode
- [ ] Watermark appears on main chart
- [ ] Play advances cursor smoothly at selected speed
- [ ] Step forward/backward moves exactly one candle
- [ ] Right-of-cursor content is de-emphasized
- [ ] All panels show synchronized timestamp
- [ ] Exit replay returns to live mode
- [ ] Performance mode toggle changes UI state
- [ ] Backend /replay/window endpoint returns valid data
- [ ] Speed selector cycles through presets correctly

### Known Limitations
- Grid layout drag-and-drop not yet implemented (requires react-grid-layout)
- Panel reordering currently static
- Replay cursor visual not yet rendered on chart (needs LightweightCharts integration)
- Performance mode toggle present but not wired to WebSocket cadence changes
- Backpressure detection not implemented on server side

### Next Steps for Full Sprint 3
1. Wire replay controls to MonitorPage state
2. Add replay cursor overlay to UnderlyingChart
3. Implement future-data styling with conditional class
4. Test with real data during market hours
5. Add grid layout for panel reordering
6. Implement server-side backpressure detection