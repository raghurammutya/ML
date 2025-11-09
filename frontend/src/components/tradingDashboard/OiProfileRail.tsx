import React, { useMemo } from 'react'
import styles from './OiProfileRail.module.css'

interface OiProfileRailProps {
  data: Array<{ strike: number; callOi: number; putOi: number }>
  maxRows?: number
}

const formatCompact = (value: number): string =>
  new Intl.NumberFormat('en-IN', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)

export const OiProfileRail: React.FC<OiProfileRailProps> = ({ data, maxRows = 14 }) => {
  const rows = useMemo(
    () =>
      data
        .filter((entry) => entry.callOi > 0 || entry.putOi > 0)
        .sort((a, b) => b.strike - a.strike)
        .slice(0, maxRows),
    [data, maxRows],
  )

  const maxValue = useMemo(() => {
    const values = rows.flatMap((entry) => [entry.callOi, entry.putOi])
    return values.length ? Math.max(...values) : 0
  }, [rows])

  if (!rows.length || maxValue === 0) {
    return null
  }

  return (
    <div className={styles.rail}>
      {rows.map((row) => {
        const callWidth = Math.max((row.callOi / maxValue) * 100, 4)
        const putWidth = Math.max((row.putOi / maxValue) * 100, 4)
        return (
          <div key={row.strike} className={styles.row}>
            <div className={styles.strikeLabel}>{row.strike.toLocaleString('en-IN')}</div>
            <div className={styles.barRow}>
              <div className={styles.barValue}>{formatCompact(row.putOi)}</div>
              <div className={styles.putBar}>
                <div className={styles.putBarFill} style={{ width: `${putWidth}%` }} />
              </div>
              <div className={styles.callBar}>
                <div className={styles.callBarFill} style={{ width: `${callWidth}%` }} />
              </div>
              <div className={styles.barValue}>{formatCompact(row.callOi)}</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default OiProfileRail

