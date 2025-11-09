/**
 * Trading Account Context
 *
 * Manages state for trading accounts:
 * - Fetches owned and shared accounts
 * - Handles account selection
 * - Provides permission checking
 */

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react'
import { useAuth } from './AuthContext'
import { fetchTradingAccounts, TradingAccount, hasPermission as checkPermission } from '../services/tradingAccounts'

interface TradingAccountContextType {
  ownedAccounts: TradingAccount[]
  sharedAccounts: TradingAccount[]
  allAccounts: TradingAccount[]
  selectedAccount: TradingAccount | null
  selectAccount: (accountId: number) => void
  refreshAccounts: () => Promise<void>
  hasPermission: (permission: 'view' | 'trade' | 'manage') => boolean
  loading: boolean
  error: string | null
}

const TradingAccountContext = createContext<TradingAccountContextType | null>(null)

export const TradingAccountProvider = ({ children }: { children: ReactNode }) => {
  const { accessToken, user } = useAuth()
  const [ownedAccounts, setOwnedAccounts] = useState<TradingAccount[]>([])
  const [sharedAccounts, setSharedAccounts] = useState<TradingAccount[]>([])
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadAccounts = useCallback(async () => {
    if (!accessToken) {
      setLoading(false)
      return
    }

    try {
      setLoading(true)
      setError(null)
      const data = await fetchTradingAccounts(accessToken)
      setOwnedAccounts(data.owned_accounts)
      setSharedAccounts(data.shared_accounts)

      // Auto-select first account if none selected
      if (!selectedAccountId) {
        if (data.owned_accounts.length > 0) {
          setSelectedAccountId(data.owned_accounts[0].trading_account_id)
        } else if (data.shared_accounts.length > 0) {
          setSelectedAccountId(data.shared_accounts[0].trading_account_id)
        }
      }
    } catch (err: any) {
      console.error('[TradingAccountContext] Failed to load accounts:', err)
      setError(err.message || 'Failed to load trading accounts')
    } finally {
      setLoading(false)
    }
  }, [accessToken, selectedAccountId])

  // Load accounts on mount and when auth changes
  useEffect(() => {
    loadAccounts()
  }, [loadAccounts])

  // Clear accounts on logout
  useEffect(() => {
    if (!user) {
      setOwnedAccounts([])
      setSharedAccounts([])
      setSelectedAccountId(null)
      setError(null)
    }
  }, [user])

  const allAccounts = [...ownedAccounts, ...sharedAccounts]
  const selectedAccount = allAccounts.find(acc => acc.trading_account_id === selectedAccountId) || null

  const hasPermission = (permission: 'view' | 'trade' | 'manage'): boolean => {
    return checkPermission(selectedAccount, permission)
  }

  const selectAccount = (accountId: number) => {
    const account = allAccounts.find(acc => acc.trading_account_id === accountId)
    if (account) {
      setSelectedAccountId(accountId)
      console.log('[TradingAccountContext] Selected account:', account.account_name, `(${account.broker_user_id})`)
    }
  }

  return (
    <TradingAccountContext.Provider
      value={{
        ownedAccounts,
        sharedAccounts,
        allAccounts,
        selectedAccount,
        selectAccount,
        refreshAccounts: loadAccounts,
        hasPermission,
        loading,
        error
      }}
    >
      {children}
    </TradingAccountContext.Provider>
  )
}

export const useTradingAccount = () => {
  const context = useContext(TradingAccountContext)
  if (!context) {
    throw new Error('useTradingAccount must be used within TradingAccountProvider')
  }
  return context
}
