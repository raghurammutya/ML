# TradingView Visualization Frontend

This frontend provides two ways to visualize NIFTY50 data with ML labels:

## 📊 Chart Options

### 1. **TradingView Widget (Default)**
- Uses TradingView's free Advanced Chart Widget
- Shows live NIFTY data from TradingView's servers
- Cannot display your custom ML labels directly on the chart
- ML predictions shown in overlay panel
- No setup required - works immediately

### 2. **Custom Chart**
- Uses Recharts to display your TimescaleDB data
- Shows ML labels directly on the chart as colored dots
- Full integration with your backend
- Complete control over visualization

## 🚀 Getting Started

### Development Mode
```bash
npm install
npm run dev
```

### Production Build
```bash
npm run build
```

## 🎯 Key Features

1. **Dual Chart View**
   - Toggle between TradingView widget and custom chart
   - Both charts show your ML predictions
   - Real-time data updates

2. **ML Label Integration**
   - Recent predictions overlay
   - Label distribution statistics
   - Color-coded sentiment indicators

3. **Performance Monitoring**
   - Cache hit rate display
   - Response time tracking
   - System health indicators

## 🔧 Configuration

### TradingView Widget
The widget is configured in `TradingViewWidget.tsx`:
- Symbol: NSE:NIFTY (TradingView's symbol)
- Theme: Dark
- Indicators: SMA, RSI
- Timezone: Asia/Kolkata

### Custom Chart
The custom chart in `CustomChartWithMLLabels.tsx`:
- Uses your backend data via UDF protocol
- Displays ML labels as colored markers
- Updates every minute

## 📝 Notes

### TradingView Widget Limitations
- Shows TradingView's data, not your database
- Cannot modify the chart data
- ML labels shown separately

### Custom Chart Advantages
- Full control over data display
- Direct ML label integration
- Uses your cached data for performance

### For Full TradingView Integration
If you need to display your custom data in TradingView charts:
1. Apply for the TradingView Charting Library
2. This is different from the widget - it's a self-hosted solution
3. Allows complete custom data integration via UDF protocol

## 🛠️ Tech Stack
- React 18 with TypeScript
- Vite for fast development
- Recharts for custom visualization
- TradingView Advanced Chart Widget
- Axios for API calls