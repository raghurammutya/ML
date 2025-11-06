import React from 'react'
import styles from './NotificationIcon.module.css'
import { NotificationIconProps } from './tradingDashboard/types'

export const MessagesIcon: React.FC<NotificationIconProps> = ({ count = 0, onClick }) => (
  <button
    type="button"
    className={styles.button}
    onClick={onClick}
    title={`${count} message${count === 1 ? '' : 's'}`}
    aria-label={count > 0 ? `${count} unread messages` : 'No unread messages'}
  >
    <svg className={styles.icon} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
      />
    </svg>
    {count > 0 && (
      <span className={`${styles.badge} ${styles.badgeMessage}`}>{count > 99 ? '99' : count}</span>
    )}
  </button>
)

