import React, { Fragment, useState } from 'react'
import { Menu, Transition } from '@headlessui/react'

/**
 * UserMenuDropdown - User profile dropdown with global settings
 *
 * This component renders a circular avatar that opens a dropdown menu
 * containing user preferences and actions.
 *
 * Features:
 * - Theme toggle (light/dark)
 * - Layout preferences
 * - Settings
 * - Logout
 *
 * Accessibility:
 * - Keyboard navigation (Tab, Enter, Escape)
 * - Focus management
 * - ARIA labels
 */

interface UserMenuDropdownProps {
  userName?: string
  userEmail?: string
  userAvatar?: string
  onThemeToggle?: () => void
  onLogout?: () => void
}

export const UserMenuDropdown: React.FC<UserMenuDropdownProps> = ({
  userName = 'User',
  userEmail = 'user@example.com',
  userAvatar,
  onThemeToggle,
  onLogout,
}) => {
  const [currentTheme, setCurrentTheme] = useState<'light' | 'dark'>('dark')

  const handleThemeToggle = () => {
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark'
    setCurrentTheme(newTheme)
    onThemeToggle?.()
  }

  const handleLogout = () => {
    if (confirm('Are you sure you want to logout?')) {
      onLogout?.()
    }
  }

  // Get user initials from name
  const getInitials = (name: string): string => {
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }

  return (
    <Menu as="div" className="relative">
      {/* Avatar Button */}
      <Menu.Button className="flex items-center gap-2 h-10 px-3 bg-gray-800/50 hover:bg-gray-800 rounded-lg border border-gray-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500">
        {/* Avatar */}
        <div className="w-7 h-7 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
          {userAvatar ? (
            <img
              src={userAvatar}
              alt={userName}
              className="w-full h-full rounded-full object-cover"
            />
          ) : (
            <span className="text-white text-xs font-semibold">
              {getInitials(userName)}
            </span>
          )}
        </div>

        {/* User Name (hidden on small screens) */}
        <span className="text-sm text-gray-300 hidden lg:inline">{userName}</span>

        {/* Chevron Icon */}
        <svg
          className="w-4 h-4 text-gray-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </Menu.Button>

      {/* Dropdown Menu */}
      <Transition
        as={Fragment}
        enter="transition ease-out duration-100"
        enterFrom="transform opacity-0 scale-95"
        enterTo="transform opacity-100 scale-100"
        leave="transition ease-in duration-75"
        leaveFrom="transform opacity-100 scale-100"
        leaveTo="transform opacity-0 scale-95"
      >
        <Menu.Items className="absolute left-0 mt-2 w-64 origin-top-left bg-gray-800 border border-gray-700 rounded-lg shadow-xl focus:outline-none z-50">
          {/* User Info Section */}
          <div className="px-4 py-3 border-b border-gray-700">
            <p className="text-sm font-medium text-white">{userName}</p>
            <p className="text-xs text-gray-400 truncate">{userEmail}</p>
          </div>

          {/* Menu Items */}
          <div className="py-1">
            {/* Theme Toggle */}
            <Menu.Item>
              {({ active }) => (
                <button
                  onClick={handleThemeToggle}
                  className={`${
                    active ? 'bg-gray-700' : ''
                  } group flex w-full items-center justify-between px-4 py-2 text-sm text-gray-300 transition-colors`}
                >
                  <span className="flex items-center gap-3">
                    {currentTheme === 'dark' ? (
                      <svg
                        className="w-5 h-5 text-gray-400"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
                        />
                      </svg>
                    ) : (
                      <svg
                        className="w-5 h-5 text-gray-400"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
                        />
                      </svg>
                    )}
                    Theme
                  </span>
                  <span className="text-xs text-gray-500 capitalize">{currentTheme}</span>
                </button>
              )}
            </Menu.Item>

            {/* Layout Preferences */}
            <Menu.Item>
              {({ active }) => (
                <button
                  className={`${
                    active ? 'bg-gray-700' : ''
                  } group flex w-full items-center px-4 py-2 text-sm text-gray-300 transition-colors`}
                >
                  <svg
                    className="w-5 h-5 mr-3 text-gray-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1H5a1 1 0 01-1-1v-3zM14 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1h-4a1 1 0 01-1-1v-3z"
                    />
                  </svg>
                  Layout Preferences
                </button>
              )}
            </Menu.Item>

            {/* Settings */}
            <Menu.Item>
              {({ active }) => (
                <button
                  className={`${
                    active ? 'bg-gray-700' : ''
                  } group flex w-full items-center px-4 py-2 text-sm text-gray-300 transition-colors`}
                >
                  <svg
                    className="w-5 h-5 mr-3 text-gray-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                    />
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                    />
                  </svg>
                  Settings
                </button>
              )}
            </Menu.Item>
          </div>

          {/* Logout */}
          <div className="border-t border-gray-700">
            <Menu.Item>
              {({ active }) => (
                <button
                  onClick={handleLogout}
                  className={`${
                    active ? 'bg-gray-700' : ''
                  } group flex w-full items-center px-4 py-2 text-sm text-red-400 transition-colors`}
                >
                  <svg
                    className="w-5 h-5 mr-3"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                    />
                  </svg>
                  Logout
                </button>
              )}
            </Menu.Item>
          </div>
        </Menu.Items>
      </Transition>
    </Menu>
  )
}
