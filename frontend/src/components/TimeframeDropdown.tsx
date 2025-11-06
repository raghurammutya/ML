import React, { Fragment } from 'react'
import { Menu, Transition } from '@headlessui/react'
import styles from './TimeframeDropdown.module.css'
import { Timeframe } from './tradingDashboard/types'
import { classNames } from '../utils/classNames'

interface TimeframeDropdownProps {
  value: Timeframe
  onChange: (timeframe: Timeframe) => void
}

const TIMEFRAMES: { value: Timeframe; label: string }[] = [
  { value: '1min', label: '1 min' },
  { value: '2min', label: '2 min' },
  { value: '3min', label: '3 min' },
  { value: '5min', label: '5 min' },
  { value: '15min', label: '15 min' },
  { value: '30min', label: '30 min' },
  { value: '1hr', label: '1 hour' },
  { value: '1day', label: '1 day' },
]

export const TimeframeDropdown: React.FC<TimeframeDropdownProps> = ({ value, onChange }) => {
  const selectedLabel = TIMEFRAMES.find((timeframe) => timeframe.value === value)?.label ?? '5 min'

  return (
    <Menu as="div" className={styles.container}>
      {({ open }) => (
        <>
          <Menu.Button className={styles.trigger}>
            <svg className={styles.icon} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{selectedLabel}</span>
            <svg
              className={classNames(styles.chevron, open && styles.chevronOpen)}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </Menu.Button>

          <Transition
            as={Fragment}
            enter={styles.menuEnter}
            enterFrom={styles.menuEnterFrom}
            enterTo={styles.menuEnterTo}
            leave={styles.menuLeave}
            leaveFrom={styles.menuLeaveFrom}
            leaveTo={styles.menuLeaveTo}
          >
            <Menu.Items className={styles.menu}>
              {TIMEFRAMES.map((timeframe) => (
                <Menu.Item key={timeframe.value}>
                  {({ active }) => (
                    <button
                      type="button"
                      onClick={() => onChange(timeframe.value)}
                      className={classNames(
                        styles.menuItem,
                        active && styles.menuItemActive,
                        value === timeframe.value && styles.menuItemSelected,
                      )}
                    >
                      {timeframe.label}
                      {value === timeframe.value && (
                        <svg className={styles.menuCheck} viewBox="0 0 20 20" fill="currentColor">
                          <path
                            fillRule="evenodd"
                            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                            clipRule="evenodd"
                          />
                        </svg>
                      )}
                    </button>
                  )}
                </Menu.Item>
              ))}
            </Menu.Items>
          </Transition>
        </>
      )}
    </Menu>
  )
}

