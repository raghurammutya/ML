import React from 'react'
import styles from './ReplayToggleSwitch.module.css'
import { ReplayToggleSwitchProps } from './tradingDashboard/types'
import { classNames } from '../utils/classNames'

const SPEED_OPTIONS = [1, 2, 5, 10]

export const ReplayToggleSwitch: React.FC<ReplayToggleSwitchProps> = ({
  enabled,
  onToggle,
  speed = 1,
  onSpeedChange,
}) => {
  return (
    <div className={styles.wrapper}>
      <button
        type="button"
        className={classNames(styles.toggle, enabled && styles.toggleActive)}
        onClick={() => onToggle(!enabled)}
        title={enabled ? 'Disable replay mode' : 'Enable replay mode'}
      >
        <svg className={styles.icon} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span className={styles.label}>Replay</span>
      </button>

      {enabled && onSpeedChange && (
        <div className={styles.speedGroup}>
          {SPEED_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => onSpeedChange(option)}
              className={classNames(styles.speedButton, speed === option && styles.speedButtonActive)}
            >
              {option}x
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

