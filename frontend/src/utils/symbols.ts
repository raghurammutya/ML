const stripExchangePrefix = (symbol: string): string => {
  if (!symbol.includes(':')) return symbol
  const parts = symbol.split(':')
  return parts[parts.length - 1] ?? symbol
}

export const normalizeUnderlyingSymbol = (symbol: string): string => {
  const trimmed = symbol.trim()
  if (!trimmed) return ''
  const withoutPrefix = stripExchangePrefix(trimmed)
  const compact = withoutPrefix.replace(/\s+/g, '').toUpperCase()

  if (['NIFTY50', '^NSEI', 'NSEI', 'NIFTY', 'CNXNIFTY', 'NIFTY50INDEX'].includes(compact)) {
    return 'NIFTY'
  }
  if (['BANKNIFTY50', 'BANKNIFTY', 'NIFTYBANK'].includes(compact)) {
    return 'BANKNIFTY'
  }
  return compact
}

export const displayUnderlyingSymbol = (symbol: string): string => {
  const normalized = normalizeUnderlyingSymbol(symbol)
  if (!normalized) return ''
  if (normalized === 'NIFTY') {
    return 'NIFTY50'
  }
  return normalized
}
