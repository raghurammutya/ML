import React from 'react'
import Select, { MultiValue, StylesConfig } from 'react-select'
import { MOCK_INDICATOR_OPTIONS } from './tradingDashboard/types'

/**
 * IndicatorDropdown - Multi-select dropdown for chart indicators
 *
 * This component provides a dropdown to select multiple chart indicators
 * (e.g., RSI, MACD, Bollinger Bands, Moving Average).
 */

export interface IndicatorOption {
  value: string
  label: string
}

interface IndicatorDropdownProps {
  selected: string[]
  onChange: (indicators: string[]) => void
  options?: IndicatorOption[]
}

export const IndicatorDropdown: React.FC<IndicatorDropdownProps> = ({
  selected,
  onChange,
  options,
}) => {
  const handleChange = (selectedOptions: MultiValue<IndicatorOption>) => {
    const indicators = selectedOptions ? selectedOptions.map((opt) => opt.value) : []
    onChange(indicators)
  }

  const indicatorOptions = options && options.length > 0 ? options : MOCK_INDICATOR_OPTIONS
  const selectedValues = indicatorOptions.filter((ind) => selected.includes(ind.value))

  // Custom dark theme styles for react-select
  const customStyles: StylesConfig<IndicatorOption, true> = {
    control: (provided, state) => ({
      ...provided,
      backgroundColor: 'rgba(31, 41, 55, 0.5)',
      borderColor: state.isFocused ? '#3b82f6' : '#374151',
      borderWidth: '1px',
      borderRadius: '0.375rem',
      minHeight: '2.25rem',
      height: '2.25rem',
      boxShadow: state.isFocused ? '0 0 0 2px rgba(59, 130, 246, 0.5)' : 'none',
      '&:hover': {
        backgroundColor: 'rgba(55, 65, 81, 0.7)',
        borderColor: state.isFocused ? '#3b82f6' : '#4b5563',
      },
      cursor: 'pointer',
      minWidth: '320px',
      width: '340px',
      maxWidth: '420px',
    }),
    valueContainer: (provided) => ({
      ...provided,
      padding: '0 0.5rem',
      height: '2.25rem',
      display: 'flex',
      flexWrap: 'wrap',
      gap: '4px',
      alignItems: 'center',
      overflow: 'hidden',
    }),
    input: (provided) => ({
      ...provided,
      color: '#d1d5db',
      margin: 0,
      padding: 0,
    }),
    placeholder: (provided) => ({
      ...provided,
      color: '#9ca3af',
      fontSize: '0.75rem',
      fontWeight: '500',
    }),
    menu: (provided) => ({
      ...provided,
      backgroundColor: '#1f2937',
      borderColor: '#374151',
      borderWidth: '1px',
      borderRadius: '0.375rem',
      marginTop: '0.25rem',
      boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.3)',
      zIndex: 60,
      minWidth: '340px',
    }),
    menuList: (provided) => ({
      ...provided,
      padding: '0.25rem',
      maxHeight: '280px',
    }),
    option: (provided, state) => ({
      ...provided,
      backgroundColor: state.isFocused ? '#374151' : state.isSelected ? 'rgba(55, 65, 81, 0.5)' : 'transparent',
      color: state.isSelected ? '#60a5fa' : '#d1d5db',
      fontSize: '0.75rem',
      fontWeight: '500',
      padding: '0.375rem 0.75rem',
      cursor: 'pointer',
      '&:active': {
        backgroundColor: '#4b5563',
      },
    }),
    multiValue: (provided) => ({
      ...provided,
      backgroundColor: '#374151',
      borderRadius: '0.25rem',
      margin: '0',
      maxWidth: '120px',
    }),
    multiValueLabel: (provided) => ({
      ...provided,
      color: '#d1d5db',
      fontSize: '0.6875rem',
      fontWeight: '500',
      padding: '0.125rem 0.25rem',
    }),
    multiValueRemove: (provided) => ({
      ...provided,
      color: '#9ca3af',
      cursor: 'pointer',
      '&:hover': {
        backgroundColor: '#4b5563',
        color: '#f87171',
      },
    }),
    indicatorSeparator: () => ({
      display: 'none',
    }),
    dropdownIndicator: (provided) => ({
      ...provided,
      color: '#6b7280',
      padding: '0 0.5rem',
      '&:hover': {
        color: '#9ca3af',
      },
    }),
    clearIndicator: (provided) => ({
      ...provided,
      color: '#6b7280',
      padding: '0 0.5rem',
      cursor: 'pointer',
      '&:hover': {
        color: '#f87171',
      },
    }),
  }

  return (
    <Select<IndicatorOption, true>
      isMulti
      options={indicatorOptions}
      value={selectedValues}
      onChange={handleChange}
      placeholder="Indicators"
      styles={customStyles}
      closeMenuOnSelect={false}
      isClearable
      isSearchable
      noOptionsMessage={() => 'No indicators found'}
    />
  )
}
