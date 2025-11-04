import React, { useState } from 'react'
import type { GlobalHeaderProps } from '../../types/monitor-v2'

export const GlobalHeader: React.FC<GlobalHeaderProps> = ({
  user,
  accounts,
  selectedAccountId,
  onAccountSelect,
  activeUniverse,
  universes,
  onUniverseChange,
  onAddUniverse,
  theme,
  onThemeChange,
  onLogout,
}) => {
  const [showUserMenu, setShowUserMenu] = useState(false)

  return (
    <header className="sticky top-0 z-50 bg-gray-900 border-b border-gray-700 shadow-lg">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between px-4 md:px-6 py-3 md:py-4 gap-4 md:gap-6">
        {/* Left: Logo & Universes */}
        <div className="flex flex-wrap items-center gap-4 md:gap-6">
          <div className="flex items-center gap-3">
            <div className="text-2xl font-black text-white bg-gradient-to-r from-blue-600 to-purple-600 px-4 py-2 rounded-lg shadow-lg">
              MonitorV2
            </div>
            <div className="text-xs font-bold text-green-400 bg-green-900/30 px-2 py-1 rounded border border-green-500">
              NEW LAYOUT
            </div>
          </div>

          {/* Universe Tabs */}
          <div className="flex items-center gap-4">
            {universes.map((universe) => (
              <button
                key={universe}
                onClick={() => onUniverseChange(universe)}
                className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  activeUniverse === universe
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
              >
                {universe}
              </button>
            ))}
            <button
              onClick={onAddUniverse}
              className="w-8 h-8 flex items-center justify-center rounded-full bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-300 transition-colors"
              title="Add Universe"
            >
              +
            </button>
          </div>
        </div>

        {/* Right: Accounts & User */}
        <div className="flex flex-wrap items-center gap-3 md:gap-4">
          {/* Trading Accounts */}
          <div className="flex items-center gap-2">
            {accounts.map((account) => (
              <button
                key={account.id}
                onClick={() => onAccountSelect(account.id)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                  selectedAccountId === account.id
                    ? 'bg-green-600 text-white ring-2 ring-green-400'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
                title={`${account.name} - ${account.broker}`}
              >
                <span className="inline-block w-2 h-2 rounded-full mr-1.5"
                  style={{
                    backgroundColor: account.accountType === 'live' ? '#10b981' :
                                     account.accountType === 'paper' ? '#f59e0b' : '#6b7280'
                  }}
                />
                {account.name}
              </button>
            ))}
          </div>

          {/* User Menu */}
          <div className="relative">
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              className="w-9 h-9 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-semibold hover:ring-2 ring-blue-400 transition-all"
              title={user.name}
            >
              {user.avatar ? (
                <img src={user.avatar} alt={user.name} className="w-full h-full rounded-full" />
              ) : (
                <span>{user.name.charAt(0).toUpperCase()}</span>
              )}
            </button>

            {showUserMenu && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setShowUserMenu(false)}
                />
                <div className="absolute right-0 mt-2 w-56 bg-gray-800 rounded-lg shadow-xl border border-gray-700 py-2 z-50">
                  <div className="px-4 py-2 border-b border-gray-700">
                    <div className="text-sm font-medium text-white">{user.name}</div>
                    <div className="text-xs text-gray-400">{user.email}</div>
                  </div>

                  <button className="w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-gray-700 transition-colors">
                    👤 Profile
                  </button>
                  <button className="w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-gray-700 transition-colors">
                    ⚙️ Settings
                  </button>

                  <div className="px-4 py-2 border-t border-gray-700">
                    <label className="flex items-center justify-between text-sm text-gray-300 cursor-pointer">
                      <span>🌙 Theme</span>
                      <select
                        value={theme}
                        onChange={(e) => onThemeChange(e.target.value as any)}
                        className="bg-gray-700 text-gray-200 rounded px-2 py-1 text-xs border-none"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <option value="dark">Dark</option>
                        <option value="light">Light</option>
                        <option value="auto">Auto</option>
                      </select>
                    </label>
                  </div>

                  <button
                    onClick={onLogout}
                    className="w-full px-4 py-2 text-left text-sm text-red-400 hover:bg-gray-700 border-t border-gray-700 transition-colors"
                  >
                    🚪 Logout
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </header>
  )
}
