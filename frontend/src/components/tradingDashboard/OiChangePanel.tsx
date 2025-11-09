import React, { useMemo } from 'react'
import styles from './OiChangePanel.module.css'

interface OiChangeEntry {
  label: string
  callOi: number
  putOi: number
  callOiChange: number
  putOiChange: number
  pcr?: number | null
  maxPain?: number | null
}

interface OiChangePanelProps {
  entries: OiChangeEntry[]
}

const formatCompact = (value: number, digits = 1): string =>
  new Intl.NumberFormat('en-IN', {
    notation: 'compact',
    maximumFractionDigits: digits,
  }).format(value)

export const OiChangePanel: React.FC<OiChangePanelProps> = ({ entries }) => {
  const filtered = entries.filter(
    (entry) => entry.callOiChange !== 0 || entry.putOiChange !== 0 || entry.callOi || entry.putOi,
  )
  const maxMagnitude = useMemo(() => {
    const values = filtered.flatMap((entry) => [
      Math.abs(entry.callOiChange),
      Math.abs(entry.putOiChange),
    ])
    return values.length ? Math.max(...values) : 0
  }, [filtered])

  if (!filtered.length) return null

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span>OI Change (filtered moneyness)</span>
        <span>{new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</span>
      </div>
      <div className={styles.rows}>
        {filtered.map((entry) => {
          const callWidth =
            maxMagnitude > 0 ? Math.abs(entry.callOiChange) / maxMagnitude : 0
          const putWidth =
            maxMagnitude > 0 ? Math.abs(entry.putOiChange) / maxMagnitude : 0
          return (
            <div key={entry.label} className={styles.row}>
              <div className={styles.rowLabel}>
                <span>{entry.label}</span>
                <span>
                  C:{formatCompact(entry.callOi)} · P:{formatCompact(entry.putOi)}
                  {entry.maxPain ? ` · MP:${entry.maxPain.toLocaleString('en-IN')}` : ''}
                  {entry.pcr != null ? ` · PCR:${entry.pcr.toFixed(2)}` : ''}
                </span>
              </div>
              <div className={styles.barTrack}>
                {putWidth > 0 && (
                  <div
                    className={styles.putChange}
                    style={{ width: `${putWidth * 50}%` }}
                    title={`Put Δ ${formatCompact(entry.putOiChange, 2)}`}
                  />
                )}
                {callWidth > 0 && (
                  <div
                    className={styles.callChange}
                    style={{ width: `${callWidth * 50}%` }}
                    title={`Call Δ ${formatCompact(entry.callOiChange, 2)}`}
                  />
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default OiChangePanel

