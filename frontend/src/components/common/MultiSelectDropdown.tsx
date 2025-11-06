import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import styles from './MultiSelectDropdown.module.css'

export interface MultiSelectOption {
  value: string
  label: string
}

interface MultiSelectDropdownProps {
  label: string
  options: MultiSelectOption[]
  selected: string[]
  placeholder?: string
  onChange: (values: string[]) => void
}

export const MultiSelectDropdown: React.FC<MultiSelectDropdownProps> = ({
  label,
  options,
  selected,
  placeholder = 'Select…',
  onChange,
}) => {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)

  const toggleOpen = useCallback(() => setOpen((prev) => !prev), [])

  useEffect(() => {
    const handleClickAway = (event: MouseEvent) => {
      if (!containerRef.current) return
      if (event.target instanceof Node && containerRef.current.contains(event.target)) {
        return
      }
      setOpen(false)
    }
    document.addEventListener('mousedown', handleClickAway)
    return () => document.removeEventListener('mousedown', handleClickAway)
  }, [])

  const handleToggleValue = useCallback(
    (value: string) => {
      setOpen(true)
      onChange(
        selected.includes(value)
          ? selected.filter((item) => item !== value)
          : [...selected, value],
      )
    },
    [onChange, selected],
  )

  const summary = useMemo(() => {
    if (!selected.length) {
      return placeholder
    }
    if (selected.length === options.length) {
      return 'All selected'
    }
    if (selected.length === 1) {
      const option = options.find((item) => item.value === selected[0])
      return option?.label ?? selected[0]
    }
    return `${selected.length} selected`
  }, [options, placeholder, selected])

  return (
    <div className={styles.wrapper} ref={containerRef}>
      <button type="button" className={styles.trigger} onClick={toggleOpen}>
        <span className={styles.triggerLabel}>{label}</span>
        <span className={styles.triggerValue}>{summary}</span>
        <span className={styles.chevron} data-open={open}>
          ▾
        </span>
      </button>
      {open && (
        <div className={styles.menu}>
          {options.map((option) => {
            const checked = selected.includes(option.value)
            return (
              <label key={option.value} className={styles.option}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => handleToggleValue(option.value)}
                />
                <span>{option.label}</span>
              </label>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default MultiSelectDropdown
