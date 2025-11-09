const currencyFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
})

const compactFormatter = new Intl.NumberFormat('en-IN', {
  maximumFractionDigits: 1,
})

export const formatCurrency = (value: number | null | undefined): string => {
  if (value == null || Number.isNaN(value)) {
    return '₹0.00'
  }
  return currencyFormatter.format(value)
}

export const formatNumber = (value: number | null | undefined): string => {
  if (value == null || Number.isNaN(value)) {
    return '0'
  }
  return compactFormatter.format(value)
}
