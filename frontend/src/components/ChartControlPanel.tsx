import React, { useCallback } from 'react'
import styles from './ChartControlPanel.module.css'
import { SaveLayoutButton } from './SaveLayoutButton'
import { LoadLayoutButton } from './LoadLayoutButton'
import { ReplayToggleSwitch } from './ReplayToggleSwitch'
import { TimeframeDropdown } from './TimeframeDropdown'
import { IndicatorDropdown } from './IndicatorDropdown'
import { AlertsIcon } from './AlertsIcon'
import { MessagesIcon } from './MessagesIcon'
import { ChartControlPanelProps } from './tradingDashboard/types'
import { MultiSelectDropdown } from './common/MultiSelectDropdown'

export const ChartControlPanel: React.FC<ChartControlPanelProps> = ({
  onSaveLayout,
  onLoadLayout,
  replayEnabled,
  onReplayToggle,
  replaySpeed,
  onReplaySpeedChange,
  timeframe,
  onTimeframeChange,
  selectedIndicators,
  onIndicatorsChange,
  alertCount = 0,
  messageCount = 0,
  onAlertsClick,
  onMessagesClick,
  indicatorOptions,
  expiryOptions,
  selectedExpiries = [],
  onExpiriesChange,
  moneynessOptions,
  selectedMoneyness = [],
  onMoneynessChange,
}) => {
  const handleSave = useCallback(() => {
    console.log('Save layout clicked')
    onSaveLayout?.()
  }, [onSaveLayout])

  const handleLoad = useCallback(() => {
    console.log('Load layout clicked')
    onLoadLayout?.()
  }, [onLoadLayout])

  return (
    <div className={styles.wrapper}>
      <div className={styles.group}>
        <SaveLayoutButton onSave={handleSave} />
        <LoadLayoutButton onLoad={handleLoad} />
      </div>

      <div className={styles.separator} />

      <ReplayToggleSwitch enabled={replayEnabled} onToggle={onReplayToggle} speed={replaySpeed} onSpeedChange={onReplaySpeedChange} />

      <div className={styles.separator} />

      <div className={styles.group}>
        <TimeframeDropdown value={timeframe} onChange={onTimeframeChange} />
        <IndicatorDropdown selected={selectedIndicators} onChange={onIndicatorsChange} options={indicatorOptions} />
      </div>

      <div className={styles.separator} />

      <div className={styles.group}>
        <AlertsIcon count={alertCount} onClick={onAlertsClick} />
        <MessagesIcon count={messageCount} onClick={onMessagesClick} />
      </div>

      {(expiryOptions || moneynessOptions) && <div className={styles.separator} />}

      <div className={styles.filters}>
        {expiryOptions && onExpiriesChange && (
          <MultiSelectDropdown
            label="Expiries"
            options={expiryOptions}
            selected={selectedExpiries}
            onChange={onExpiriesChange}
            placeholder="All expiries"
          />
        )}
        {moneynessOptions && onMoneynessChange && (
          <MultiSelectDropdown
            label="Moneyness"
            options={moneynessOptions}
            selected={selectedMoneyness}
            onChange={onMoneynessChange}
            placeholder="All buckets"
          />
        )}
      </div>
    </div>
  )
}
