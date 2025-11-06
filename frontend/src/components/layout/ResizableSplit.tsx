import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import styles from './ResizableSplit.module.css'
import { classNames } from '../../utils/classNames'

type Orientation = 'horizontal' | 'vertical'

interface ResizableSplitProps {
  primary: React.ReactNode
  secondary: React.ReactNode
  /**
   * Initial size of the primary pane in percentage (0-100). Defaults to 66.
   */
  initialPrimaryPercentage?: number
  /**
   * Minimum size of the primary pane in pixels. Defaults to 260.
   */
  minPrimaryPx?: number
  /**
   * Minimum size of the secondary pane in pixels. Defaults to 260.
   */
  minSecondaryPx?: number
  /**
   * Split orientation. Horizontal = side by side, Vertical = stacked. Defaults to horizontal.
   */
  orientation?: Orientation
  className?: string
  ariaLabel?: string
}

export const ResizableSplit: React.FC<ResizableSplitProps> = ({
  primary,
  secondary,
  initialPrimaryPercentage = 66,
  minPrimaryPx = 260,
  minSecondaryPx = 260,
  orientation = 'horizontal',
  className,
  ariaLabel = 'Resizable split panels',
}) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const [primaryPercentage, setPrimaryPercentage] = useState(initialPrimaryPercentage)
  const [isDragging, setIsDragging] = useState(false)

  const clampPercentage = useCallback(
    (percentage: number) => {
      const container = containerRef.current
      if (!container) return percentage
      const rect = container.getBoundingClientRect()
      const extent = orientation === 'horizontal' ? rect.width : rect.height
      if (extent <= 0) return percentage
      const minPercent = (minPrimaryPx / extent) * 100
      const maxPercent = 100 - (minSecondaryPx / extent) * 100
      if (percentage < minPercent) return minPercent
      if (percentage > maxPercent) return maxPercent
      return percentage
    },
    [minPrimaryPx, minSecondaryPx, orientation],
  )

  const startDragging = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    setIsDragging(true)
  }, [])

  const handlePointerMove = useCallback(
    (event: PointerEvent) => {
      if (!isDragging || !containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const offset =
        orientation === 'horizontal' ? event.clientX - rect.left : event.clientY - rect.top
      const extent = orientation === 'horizontal' ? rect.width : rect.height
      if (extent <= 0) return
      const percentage = (offset / extent) * 100
      setPrimaryPercentage(clampPercentage(percentage))
    },
    [clampPercentage, isDragging, orientation],
  )

  const stopDragging = useCallback(() => {
    setIsDragging(false)
  }, [])

  useEffect(() => {
    if (!isDragging) return

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', stopDragging)
    window.addEventListener('pointercancel', stopDragging)

    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', stopDragging)
      window.removeEventListener('pointercancel', stopDragging)
    }
  }, [handlePointerMove, isDragging, stopDragging])

  const primaryStyle = useMemo<React.CSSProperties>(
    () => ({ flexBasis: `${primaryPercentage}%` }),
    [primaryPercentage],
  )

  const ariaOrientation = orientation === 'horizontal' ? 'vertical' : 'horizontal'

  return (
    <div
      ref={containerRef}
      className={classNames(
        styles.container,
        orientation === 'horizontal' ? styles.horizontal : styles.vertical,
        className,
      )}
      aria-label={ariaLabel}
    >
      <div className={classNames(styles.panel, styles.primary)} style={primaryStyle}>
        {primary}
      </div>

      <div
        role="separator"
        aria-orientation={ariaOrientation}
        aria-label="Resize panels"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(primaryPercentage)}
        tabIndex={0}
        onPointerDown={startDragging}
        className={classNames(
          styles.divider,
          orientation === 'horizontal' ? styles.horizontalDivider : styles.verticalDivider,
          isDragging && styles.dragging,
        )}
      >
        <div className={styles.overlay} />
        <div className={styles.dividerHandle} />
      </div>

      <div className={classNames(styles.panel, styles.secondary)}>{secondary}</div>
    </div>
  )
}

