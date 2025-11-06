import React from 'react'
import styles from './ControlButton.module.css'

interface LoadLayoutButtonProps {
  onLoad: () => void
  disabled?: boolean
}

export const LoadLayoutButton: React.FC<LoadLayoutButtonProps> = ({ onLoad, disabled = false }) => (
  <button type="button" onClick={onLoad} disabled={disabled} className={styles.button} title="Load layout">
    <svg className={styles.icon} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
    </svg>
    <span className={styles.label}>Load</span>
  </button>
)
