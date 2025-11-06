import React, { Fragment, useState } from 'react'
import { Menu, Transition } from '@headlessui/react'
import styles from './UserMenuDropdown.module.css'
import { UserMenuDropdownProps } from './tradingDashboard/types'
import { classNames } from '../utils/classNames'

const SunIcon = () => (
  <svg className={styles.menuIcon} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
    />
  </svg>
)

const MoonIcon = () => (
  <svg className={styles.menuIcon} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
    />
  </svg>
)

const LayoutIcon = () => (
  <svg className={styles.menuIcon} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M4 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1H5a1 1 0 01-1-1v-3zM14 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1h-4a1 1 0 01-1-1v-3z"
    />
  </svg>
)

const CogIcon = () => (
  <svg className={styles.menuIcon} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
    />
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
)

const LogoutIcon = () => (
  <svg className={styles.menuIcon} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
  </svg>
)

const getInitials = (name: string): string =>
  name
    .split(' ')
    .map((part) => part[0])
    .filter(Boolean)
    .join('')
    .toUpperCase()
    .slice(0, 2)

export const UserMenuDropdown: React.FC<UserMenuDropdownProps> = ({
  userName = 'User',
  userEmail = 'user@example.com',
  userAvatar,
  onThemeToggle,
  onLogout,
}) => {
  const [currentTheme, setCurrentTheme] = useState<'light' | 'dark'>('dark')

  const handleThemeToggle = () => {
    const next = currentTheme === 'dark' ? 'light' : 'dark'
    setCurrentTheme(next)
    onThemeToggle?.()
  }

  const handleLogout = () => {
    if (confirm('Are you sure you want to logout?')) {
      onLogout?.()
    }
  }

  return (
    <Menu as="div" className={styles.container}>
      {({ open }) => (
        <>
          <Menu.Button className={styles.trigger}>
            <span className={styles.avatar}>
              {userAvatar ? (
                <img src={userAvatar} alt={userName} className={styles.avatarImage} />
              ) : (
                getInitials(userName)
              )}
            </span>
            <span className={styles.triggerLabel}>{userName}</span>
            <svg
              className={classNames(styles.chevron, open && styles.chevronOpen)}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={2}
              aria-hidden="true"
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
              <div className={styles.menuHeader}>
                <p className={styles.menuTitle}>{userName}</p>
                <p className={styles.menuSubtitle}>{userEmail}</p>
              </div>

              <div className={styles.menuSection}>
                <Menu.Item>
                  {({ active }) => (
                    <button
                      type="button"
                      onClick={handleThemeToggle}
                      className={classNames(styles.menuItem, active && styles.menuItemActive)}
                    >
                      <span className={styles.menuLabel}>
                        {currentTheme === 'dark' ? <MoonIcon /> : <SunIcon />}
                        Theme
                      </span>
                      <span className={styles.menuSuffix}>{currentTheme}</span>
                    </button>
                  )}
                </Menu.Item>

                <Menu.Item>
                  {({ active }) => (
                    <button type="button" className={classNames(styles.menuItem, active && styles.menuItemActive)}>
                      <span className={styles.menuLabel}>
                        <LayoutIcon />
                        Layout preferences
                      </span>
                    </button>
                  )}
                </Menu.Item>

                <Menu.Item>
                  {({ active }) => (
                    <button type="button" className={classNames(styles.menuItem, active && styles.menuItemActive)}>
                      <span className={styles.menuLabel}>
                        <CogIcon />
                        Settings
                      </span>
                    </button>
                  )}
                </Menu.Item>
              </div>

              <div className={styles.menuDivider} />

              <div className={styles.menuSection}>
                <Menu.Item>
                  {({ active }) => (
                    <button
                      type="button"
                      onClick={handleLogout}
                      className={classNames(styles.menuItem, active && styles.menuItemActive, styles.danger)}
                    >
                      <span className={styles.menuLabel}>
                        <LogoutIcon />
                        Logout
                      </span>
                    </button>
                  )}
                </Menu.Item>
              </div>
            </Menu.Items>
          </Transition>
        </>
      )}
    </Menu>
  )
}

