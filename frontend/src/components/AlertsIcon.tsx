import React from 'react'
import styles from './NotificationIcon.module.css'
import { NotificationIconProps } from './tradingDashboard/types'

export const AlertsIcon: React.FC<NotificationIconProps> = ({ count = 0, onClick }) => (
  <button
    type="button"
    className={styles.button}
    onClick={onClick}
    title={`${count} alert${count === 1 ? '' : 's'}`}
    aria-label={count > 0 ? `${count} active alerts` : 'No active alerts'}
  >
    <svg className={styles.icon} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
      />
    </svg>
    {count > 0 && (
      <span className={`${styles.badge} ${styles.badgeAlert}`}>{count > 99 ? '99' : count}</span>
    )}
  </button>
)

