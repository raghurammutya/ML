import ReactDOM from 'react-dom/client'
import App from './App'
import MonitorPage from './pages/MonitorPage'
import MonitorV2 from './pages/MonitorV2'
import TradingDashboard from './pages/TradingDashboard'
import './index.css'

const pathname = window.location.pathname

// Route selection
let RootComponent = App
if (pathname.startsWith('/trading-dashboard') || pathname.startsWith('/trading-dashboard/')) {
  RootComponent = TradingDashboard
} else if (pathname.startsWith('/monitor-v2') || pathname.startsWith('/monitor-v2/')) {
  RootComponent = MonitorV2
} else if (pathname.startsWith('/monitor') || pathname.startsWith('/monitor/') ||
           pathname.startsWith('/nifty-monitor') || pathname.startsWith('/nifty-monitor/')) {
  RootComponent = MonitorPage
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <RootComponent />
)
