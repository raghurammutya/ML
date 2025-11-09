import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react'
import { Strategy } from '../types/strategy'
import { useAuth } from './AuthContext'
import { useTradingAccount } from './TradingAccountContext'
import { fetchStrategies } from '../services/strategies'

export interface StrategyContextType {
  strategies: Strategy[]
  selectedStrategy: Strategy | null
  selectStrategy: (strategyId: number) => void
  refreshStrategies: () => Promise<void>
  loading: boolean
  error: string | null
}

const StrategyContext = createContext<StrategyContextType | null>(null)

export const StrategyProvider = ({ children }: { children: ReactNode }) => {
  const { accessToken } = useAuth()
  const { selectedAccount } = useTradingAccount()

  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [selectedStrategyId, setSelectedStrategyId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadStrategies = useCallback(async () => {
    if (!accessToken || !selectedAccount) {
      setStrategies([])
      setSelectedStrategyId(null)
      setError(null)
      setLoading(false)
      return
    }

    try {
      setLoading(true)
      setError(null)
      const data = await fetchStrategies(accessToken, String(selectedAccount.trading_account_id))
      setStrategies(data)

      if (data.length === 0) {
        setSelectedStrategyId(null)
        return
      }

      setSelectedStrategyId((prev) => {
        if (prev && data.some((strategy) => strategy.strategy_id === prev)) {
          return prev
        }
        const defaultStrategy = data.find((strategy) => strategy.is_default)
        return defaultStrategy?.strategy_id ?? data[0].strategy_id
      })
    } catch (err: any) {
      console.error('[StrategyContext] Failed to load strategies', err)
      setError(err.message || 'Failed to load strategies')
      setStrategies([])
      setSelectedStrategyId(null)
    } finally {
      setLoading(false)
    }
  }, [accessToken, selectedAccount])

  useEffect(() => {
    loadStrategies()
  }, [loadStrategies])

  useEffect(() => {
    if (!accessToken || !selectedAccount) return
    const interval = window.setInterval(() => {
      loadStrategies().catch((err) => console.error('[StrategyContext] Polling failed', err))
    }, 30000)
    return () => window.clearInterval(interval)
  }, [accessToken, selectedAccount, loadStrategies])

  const selectStrategy = (strategyId: number) => {
    if (strategies.some((strategy) => strategy.strategy_id === strategyId)) {
      setSelectedStrategyId(strategyId)
    }
  }

  const value: StrategyContextType = {
    strategies,
    selectedStrategy: strategies.find((strategy) => strategy.strategy_id === selectedStrategyId) ?? null,
    selectStrategy,
    refreshStrategies: loadStrategies,
    loading,
    error,
  }

  return <StrategyContext.Provider value={value}>{children}</StrategyContext.Provider>
}

export const useStrategy = (): StrategyContextType => {
  const context = useContext(StrategyContext)
  if (!context) {
    throw new Error('useStrategy must be used within StrategyProvider')
  }
  return context
}
