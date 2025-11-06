import { useEffect, useState } from 'react'
import { fetchIndicatorOptions } from '../services/indicatorsCatalog'
import type { IndicatorOption } from '../components/tradingDashboard/types'
import { MOCK_INDICATOR_OPTIONS } from '../components/tradingDashboard/types'

interface IndicatorCatalogState {
  options: IndicatorOption[]
  loading: boolean
  error: string | null
}

const initialState: IndicatorCatalogState = {
  options: MOCK_INDICATOR_OPTIONS,
  loading: true,
  error: null,
}

export const useIndicatorCatalog = (): IndicatorCatalogState => {
  const [state, setState] = useState<IndicatorCatalogState>(initialState)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const options = await fetchIndicatorOptions()
        if (!cancelled) {
          setState({
            options: options.length ? options : MOCK_INDICATOR_OPTIONS,
            loading: false,
            error: null,
          })
        }
      } catch (error: any) {
        console.error('[useIndicatorCatalog] load error', error)
        if (!cancelled) {
          setState({ options: MOCK_INDICATOR_OPTIONS, loading: false, error: error?.message ?? 'Failed to load indicators' })
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
