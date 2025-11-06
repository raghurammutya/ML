import React, { useCallback, useMemo, useRef } from 'react'
import AsyncSelect from 'react-select/async'
import type { MultiValue, StylesConfig } from 'react-select'
import { SymbolSearchBarProps } from './tradingDashboard/types'

/**
 * SymbolSearchBar - Inline symbol search with multi-select
 *
 * This component provides a searchable dropdown for adding multiple symbols
 * as universe tabs. It integrates inline with the tab strip.
 *
 * Features:
 * - Multi-select from predefined symbol list
 * - Search/filter functionality
 * - Inline rendering with tab height
 * - Dark theme styling
 */

interface SymbolOption {
  value: string
  label: string
}

export const SymbolSearchBar: React.FC<SymbolSearchBarProps> = ({
  availableSymbols = [],
  onAddSymbols,
  placeholder = 'Add symbols...',
  onSearchSymbols,
}) => {
  const baseOptions = useMemo<SymbolOption[]>(
    () =>
      (availableSymbols ?? []).map((symbol) => ({
        value: symbol,
        label: symbol,
      })),
    [availableSymbols],
  )

  const defaultOptions = useMemo<SymbolOption[]>(() => baseOptions.slice(0, 50), [baseOptions])
  const requestIdRef = useRef(0)

  const handleChange = (selected: MultiValue<SymbolOption>) => {
    if (selected && selected.length > 0) {
      const symbols = selected.map((option) => option.value)
      onAddSymbols(symbols)
    }
  }

  const loadOptions = useCallback(
    async (inputValue: string): Promise<SymbolOption[]> => {
      const query = inputValue.trim()
      if (!onSearchSymbols) {
        if (!query) {
          return defaultOptions
        }
        const upper = query.toUpperCase()
        return baseOptions.filter((option) => option.value.includes(upper)).slice(0, 50)
      }

      if (query.length < 2) {
        const upper = query.toUpperCase()
        if (!upper) return defaultOptions
        return baseOptions
          .filter(
            (option) =>
              option.value.startsWith(upper) ||
              option.label.toUpperCase().includes(upper),
          )
          .slice(0, 50)
      }

      requestIdRef.current += 1
      const currentRequestId = requestIdRef.current
      const upper = query.toUpperCase()
      const fallback = baseOptions
        .filter(
          (option) =>
            option.value.startsWith(upper) ||
            option.label.toUpperCase().includes(upper),
        )
        .slice(0, 50)

      try {
        const results = await onSearchSymbols(query)
        if (currentRequestId !== requestIdRef.current) {
          return []
        }
        if (!Array.isArray(results) || results.length === 0) {
          return fallback
        }
        const options = results.map((symbol) => ({
          value: symbol,
          label: symbol,
        }))
        if (!options.length) {
          return fallback
        }
        return options
      } catch (error) {
        console.error('[SymbolSearchBar] search failed', error)
        return fallback
      }
    },
    [baseOptions, defaultOptions, onSearchSymbols],
  )

  // Custom dark theme styles for react-select
  const customStyles: StylesConfig<SymbolOption, true> = {
    control: (provided, state) => ({
      ...provided,
      backgroundColor: 'rgba(31, 41, 55, 0.5)', // gray-800/50
      borderColor: state.isFocused ? '#3b82f6' : '#374151', // blue-500 : gray-700
      borderWidth: '1px',
      borderRadius: '0.5rem',
      minHeight: '2.5rem',
      height: '2.5rem',
      boxShadow: state.isFocused ? '0 0 0 2px rgba(59, 130, 246, 0.5)' : 'none',
      '&:hover': {
        borderColor: state.isFocused ? '#3b82f6' : '#4b5563', // gray-600
      },
      cursor: 'text',
      width: '200px',
    }),
    valueContainer: (provided) => ({
      ...provided,
      padding: '0 0.5rem',
      height: '2.5rem',
      display: 'flex',
      flexWrap: 'nowrap',
      overflow: 'hidden',
    }),
    input: (provided) => ({
      ...provided,
      color: '#d1d5db', // gray-300
      margin: 0,
      padding: 0,
    }),
    placeholder: (provided) => ({
      ...provided,
      color: '#9ca3af', // gray-400
      fontSize: '0.875rem',
    }),
    menu: (provided) => ({
      ...provided,
      backgroundColor: '#1f2937', // gray-800
      borderColor: '#374151', // gray-700
      borderWidth: '1px',
      borderRadius: '0.5rem',
      marginTop: '0.25rem',
      boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.3)',
      zIndex: 60,
    }),
    menuList: (provided) => ({
      ...provided,
      padding: '0.25rem',
      maxHeight: '300px',
    }),
    option: (provided, state) => ({
      ...provided,
      backgroundColor: state.isFocused ? '#374151' : 'transparent', // gray-700
      color: state.isSelected ? '#60a5fa' : '#d1d5db', // blue-400 : gray-300
      fontSize: '0.875rem',
      padding: '0.5rem 0.75rem',
      cursor: 'pointer',
      '&:active': {
        backgroundColor: '#4b5563', // gray-600
      },
    }),
    multiValue: (provided) => ({
      ...provided,
      backgroundColor: '#374151', // gray-700
      borderRadius: '0.375rem',
      margin: '0 0.25rem 0 0',
      maxWidth: '60px',
    }),
    multiValueLabel: (provided) => ({
      ...provided,
      color: '#d1d5db', // gray-300
      fontSize: '0.75rem',
      padding: '0.125rem 0.375rem',
    }),
    multiValueRemove: (provided) => ({
      ...provided,
      color: '#9ca3af', // gray-400
      cursor: 'pointer',
      '&:hover': {
        backgroundColor: '#4b5563', // gray-600
        color: '#f87171', // red-400
      },
    }),
    indicatorSeparator: () => ({
      display: 'none',
    }),
    dropdownIndicator: (provided) => ({
      ...provided,
      color: '#6b7280', // gray-500
      padding: '0 0.5rem',
      '&:hover': {
        color: '#9ca3af', // gray-400
      },
    }),
    clearIndicator: (provided) => ({
      ...provided,
      color: '#6b7280', // gray-500
      padding: '0 0.5rem',
      cursor: 'pointer',
      '&:hover': {
        color: '#f87171', // red-400
      },
    }),
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center' }}>
      <AsyncSelect<SymbolOption, true>
        isMulti
        cacheOptions
        defaultOptions={defaultOptions}
        loadOptions={loadOptions}
        onChange={handleChange}
        placeholder={placeholder}
        styles={customStyles}
        closeMenuOnSelect={false}
        isClearable
        isSearchable
        value={[]}
        noOptionsMessage={() => 'No symbols found'}
        loadingMessage={() => 'Searching…'}
        components={{
          IndicatorsContainer: (props) => (
            <div {...props} style={{ display: 'flex', alignItems: 'center', paddingRight: '8px' }}>
              <svg
                width="16"
                height="16"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                strokeWidth={2}
                style={{ color: '#6b7280' }}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
              </svg>
            </div>
          ),
        }}
      />
    </div>
  )
}
