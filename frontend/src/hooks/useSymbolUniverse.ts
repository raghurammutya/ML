import { useEffect, useState } from 'react'
import { fetchUniverseSymbols } from '../services/instruments'
import { MOCK_SYMBOL_LIST } from '../components/tradingDashboard/types'

interface SymbolUniverseState {
  symbols: string[]
  loading: boolean
  error: string | null
}

const initialState: SymbolUniverseState = {
  symbols: MOCK_SYMBOL_LIST,
  loading: true,
  error: null,
}

export const useSymbolUniverse = (): SymbolUniverseState => {
  const [state, setState] = useState<SymbolUniverseState>(initialState)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const symbols = await fetchUniverseSymbols()
        if (!cancelled) {
          setState({
            symbols: symbols.length ? symbols : MOCK_SYMBOL_LIST,
            loading: false,
            error: null,
          })
        }
      } catch (error: any) {
        console.error('[useSymbolUniverse] load error', error)
        if (!cancelled) {
          setState({ symbols: MOCK_SYMBOL_LIST, loading: false, error: error?.message ?? 'Failed to load symbols' })
        }
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  return state
}
