import React from 'react'
import styles from './UniverseTabsBar.module.css'
import { SymbolSearchBar } from './SymbolSearchBar'
import { MOCK_SYMBOL_LIST, UniverseTabsBarProps } from './tradingDashboard/types'
import { classNames } from '../utils/classNames'

export const UniverseTabsBar: React.FC<UniverseTabsBarProps> = ({
  tabs,
  activeTab,
  onTabClick,
  onCloseTab,
  onAddTabs,
  availableSymbols = MOCK_SYMBOL_LIST,
  onSearchSymbols,
}) => {
  const handleAddTabs = (symbols: string[]) => {
    const newSymbols = symbols.filter((symbol: string) => !tabs.includes(symbol))
    if (newSymbols.length > 0) {
      onAddTabs(newSymbols)
    }
  }

  const handleCloseTab = (symbol: string, event: React.MouseEvent<HTMLElement>) => {
    event.stopPropagation()
    onCloseTab(symbol)
  }

  const handleCloseTabKey = (symbol: string, event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      event.stopPropagation()
      onCloseTab(symbol)
    }
  }

  const symbolsSource = availableSymbols.length ? availableSymbols : MOCK_SYMBOL_LIST

  const availableSymbolsFiltered = symbolsSource.filter((symbol: string) => !tabs.includes(symbol))

  return (
    <div className={styles.container}>
      <div className={styles.tabRegion}>
        {tabs.map((symbol) => (
          <button
            key={symbol}
            type="button"
            onClick={() => onTabClick(symbol)}
            className={classNames(styles.tabButton, activeTab === symbol && styles.tabActive)}
            aria-current={activeTab === symbol}
          >
            <span>{symbol}</span>
            <span
              className={styles.closeButton}
              role="button"
              tabIndex={0}
              aria-label={`Close ${symbol} tab`}
              onClick={(event) => handleCloseTab(symbol, event)}
              onKeyDown={(event) => handleCloseTabKey(symbol, event)}
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </span>
          </button>
        ))}
      </div>

      <div className={styles.searchRegion}>
        <SymbolSearchBar
          availableSymbols={availableSymbolsFiltered}
          onAddSymbols={handleAddTabs}
          placeholder="Add symbols..."
          onSearchSymbols={onSearchSymbols}
        />
      </div>
    </div>
  )
}
