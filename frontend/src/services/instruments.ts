import { api } from './api'

interface InstrumentSummary {
  tradingsymbol: string
  name?: string | null
  segment?: string | null
  instrument_type?: string | null
  exchange?: string | null
}

interface InstrumentListResponse {
  status: string
  total?: number
  instruments: InstrumentSummary[]
}

const ALLOWED_SEGMENTS = new Set(['INDICES', 'NSE', 'BSE'])
const DISALLOWED_SYMBOL_PATTERN = /(FUT|OPT|BOND|ETF|ETP|MF|CUR|COM|FX|WARRANT|CP|TBILL)/i

const buildQueryString = (params: Record<string, string | number | boolean | (string | number | boolean)[] | undefined>) => {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null) return
    if (Array.isArray(value)) {
      value.forEach((entry) => {
        if (entry !== undefined && entry !== null) {
          searchParams.append(key, String(entry))
        }
      })
    } else {
      searchParams.append(key, String(value))
    }
  })
  return searchParams.toString()
}

const fetchInstrumentList = async (
  params: Record<string, string | number | boolean | (string | number | boolean)[] | undefined>,
): Promise<InstrumentSummary[]> => {
  const response = await api.get<InstrumentListResponse>('/instruments/list', {
    params,
    paramsSerializer: buildQueryString,
  })
  if (response.data.status === 'success' && Array.isArray(response.data.instruments)) {
    return response.data.instruments
  }
  return []
}

const fetchFoEnabledList = async (
  params: Record<string, string | number | boolean | undefined> = {},
): Promise<InstrumentSummary[]> => {
  const response = await api.get<InstrumentListResponse>('/instruments/fo-enabled', {
    params,
    paramsSerializer: buildQueryString,
  })
  if (response.data.status === 'success' && Array.isArray(response.data.instruments)) {
    return response.data.instruments
  }
  return []
}

const dedupeSymbols = (symbols: string[]): string[] => {
  const seen = new Set<string>()
  const output: string[] = []
  symbols.forEach((symbol) => {
    const normalized = symbol.trim().toUpperCase()
    if (!seen.has(normalized)) {
      seen.add(normalized)
      output.push(normalized)
    }
  })
  return output
}

const isEligibleInstrument = (item: InstrumentSummary): boolean => {
  if (!item?.tradingsymbol) return false
  if (DISALLOWED_SYMBOL_PATTERN.test(item.tradingsymbol)) return false

  const segment = (item.segment ?? '').toUpperCase()
  const type = (item.instrument_type ?? '').toUpperCase()

  if (segment === 'INDICES') {
    return true
  }

  if (!ALLOWED_SEGMENTS.has(segment)) {
    return false
  }

  return type === 'EQ'
}

export const fetchUniverseSymbols = async (): Promise<string[]> => {
  try {
    const results = await Promise.allSettled([
      fetchInstrumentList({
        segments: ['INDICES'],
        limit: 200,
      }),
      fetchFoEnabledList({
        nse_only: true,
        limit: 500,
      }),
      fetchInstrumentList({
        segments: ['NSE', 'BSE'],
        instrument_type: 'EQ',
        limit: 1000,
      }),
    ])

    const datasets = results
      .filter((entry): entry is PromiseFulfilledResult<InstrumentSummary[]> => entry.status === 'fulfilled')
      .map((entry) => entry.value)

    const rawSymbols = datasets
      .flat()
      .filter(isEligibleInstrument)
      .map((item) => item.tradingsymbol)
      .filter(Boolean)

    const deduped = dedupeSymbols(rawSymbols)
    return deduped.sort((a, b) => a.localeCompare(b))
  } catch (error) {
    console.error('[instruments] Failed to load universe symbols', error)
    return []
  }
}

export const searchTradableSymbols = async (query: string, limit = 60): Promise<string[]> => {
  const trimmed = query.trim()
  if (!trimmed) return []

  try {
    const results = await Promise.allSettled([
      fetchInstrumentList({
        segments: ['INDICES'],
        search: trimmed,
        limit: Math.min(limit, 60),
      }),
      fetchInstrumentList({
        segments: ['NSE', 'BSE'],
        instrument_type: 'EQ',
        search: trimmed,
        limit,
      }),
      fetchFoEnabledList({
        nse_only: true,
        search: trimmed,
        limit,
      }),
    ])

    const datasets = results
      .filter((entry): entry is PromiseFulfilledResult<InstrumentSummary[]> => entry.status === 'fulfilled')
      .map((entry) => entry.value)

    const rawSymbols = datasets
      .flat()
      .filter(isEligibleInstrument)
      .map((item) => item.tradingsymbol)
      .filter(Boolean)

    const deduped = dedupeSymbols(rawSymbols)
    return deduped.slice(0, limit)
  } catch (error) {
    console.error('[instruments] Failed to search symbols', error)
    return []
  }
}
