import ReactDOM from 'react-dom/client'
import App from './App'
import MonitorPage from './pages/MonitorPage'
import './index.css'

const pathname = window.location.pathname
const monitorRoutes = ['/monitor', '/monitor/', '/nifty-monitor', '/nifty-monitor/']
const RootComponent = monitorRoutes.some(route => pathname.startsWith(route)) ? MonitorPage : App

ReactDOM.createRoot(document.getElementById('root')!).render(
  <RootComponent />
)
