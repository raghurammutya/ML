import React from 'react'
import styles from './ControlButton.module.css'

interface SaveLayoutButtonProps {
  onSave: () => void
  disabled?: boolean
}

export const SaveLayoutButton: React.FC<SaveLayoutButtonProps> = ({ onSave, disabled = false }) => (
  <button type="button" onClick={onSave} disabled={disabled} className={styles.button} title="Save layout">
    <svg className={styles.icon} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
    </svg>
    <span className={styles.label}>Save</span>
  </button>
)
