import React from 'react'
import styles from './TopControlPanel.module.css'
import { UserMenuDropdown } from './UserMenuDropdown'
import { UniverseTabsBar } from './UniverseTabsBar'
import { ChartControlPanel } from './ChartControlPanel'
import { TopControlPanelProps } from './tradingDashboard/types'

export const TopControlPanel: React.FC<TopControlPanelProps> = ({
  tabs,
  activeTab,
  onTabClick,
  onCloseTab,
  onAddTabs,
  replayEnabled,
  onReplayToggle,
  replaySpeed,
  onReplaySpeedChange,
  timeframe,
  onTimeframeChange,
  selectedIndicators,
  onIndicatorsChange,
  alertCount,
  messageCount,
  onSaveLayout,
  onLoadLayout,
  onAlertsClick,
  onMessagesClick,
  availableSymbols,
  onSearchSymbols,
  indicatorOptions,
  expiryOptions,
  selectedExpiries,
  onExpiriesChange,
  moneynessOptions,
  selectedMoneyness,
  onMoneynessChange,
}) => {
  const handleThemeToggle = () => {
    console.log('Theme toggle clicked')
  }

  const handleLogout = () => {
    console.log('Logout clicked')
  }

  return (
    <header className={styles.wrapper}>
      <div className={styles.leftZone}>
        <UserMenuDropdown
          userName="Raghuram"
          userEmail="raghuram@trading.com"
          onThemeToggle={handleThemeToggle}
          onLogout={handleLogout}
        />
      </div>

      <div className={styles.centerZone}>
        <UniverseTabsBar
          tabs={tabs}
          activeTab={activeTab}
          onTabClick={onTabClick}
          onCloseTab={onCloseTab}
          onAddTabs={onAddTabs}
          availableSymbols={availableSymbols}
          onSearchSymbols={onSearchSymbols}
        />
      </div>

      <div className={styles.rightZone}>
        <ChartControlPanel
          replayEnabled={replayEnabled}
          onReplayToggle={onReplayToggle}
          replaySpeed={replaySpeed}
          onReplaySpeedChange={onReplaySpeedChange}
          timeframe={timeframe}
          onTimeframeChange={onTimeframeChange}
          selectedIndicators={selectedIndicators}
          onIndicatorsChange={onIndicatorsChange}
          alertCount={alertCount}
          messageCount={messageCount}
          onSaveLayout={onSaveLayout}
          onLoadLayout={onLoadLayout}
          onAlertsClick={onAlertsClick}
          onMessagesClick={onMessagesClick}
          indicatorOptions={indicatorOptions}
          expiryOptions={expiryOptions}
          selectedExpiries={selectedExpiries}
          onExpiriesChange={onExpiriesChange}
          moneynessOptions={moneynessOptions}
          selectedMoneyness={selectedMoneyness}
          onMoneynessChange={onMoneynessChange}
        />
      </div>
    </header>
  )
}
