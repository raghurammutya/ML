import { api } from './api'

interface IndicatorRegistryEntry {
  name: string
  display_name?: string
  description?: string
  category?: string
}

interface IndicatorListResponse {
  status: string
  indicators: IndicatorRegistryEntry[]
}

export const fetchIndicatorOptions = async (): Promise<{ value: string; label: string }[]> => {
  try {
    const response = await api.get<IndicatorListResponse>('/indicators/list')
    if (response.data.status === 'success' && Array.isArray(response.data.indicators)) {
      return response.data.indicators.map((entry) => ({
        value: entry.name,
        label: entry.display_name || entry.name,
      }))
    }
  } catch (error) {
    console.error('[indicatorsCatalog] Failed to load indicator list', error)
  }
  return []
}
