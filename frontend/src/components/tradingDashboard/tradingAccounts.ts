export interface StrategySnapshot {
  id: string
  name: string
  symbol: string
  timeframe: string
  metrics: {
    invested: number
    roi: number
    pnl: number
    pop: number
    maxProfit: number
    maxLoss: number
    profitLeft: number
    lossLeft: number
  }
}

export interface TradingAccount {
  id: string
  username: string
  pnl: number
  roi: number
  exposureType: 'Equity' | 'Futures' | 'Options'
  strategies: StrategySnapshot[]
}

export const MOCK_TRADING_ACCOUNTS: TradingAccount[] = [
  {
    id: 'acct-shah',
    username: 'arvind.shah',
    pnl: 184250,
    roi: 12.6,
    exposureType: 'Options',
    strategies: [
      {
        id: 'strat-shah-01',
        name: 'Iron Condor Sweep',
        symbol: 'NIFTY',
        timeframe: '5',
        metrics: {
          invested: 1520000,
          roi: 12.6,
          pnl: 184250,
          pop: 68.4,
          maxProfit: 240000,
          maxLoss: 180000,
          profitLeft: 55800,
          lossLeft: 121000,
        },
      },
      {
        id: 'strat-shah-02',
        name: 'Calendar Straddle',
        symbol: 'NIFTY',
        timeframe: '15',
        metrics: {
          invested: 980000,
          roi: 8.9,
          pnl: 87240,
          pop: 61.2,
          maxProfit: 140000,
          maxLoss: 95000,
          profitLeft: 42000,
          lossLeft: 63000,
        },
      },
    ],
  },
  {
    id: 'acct-lin',
    username: 'meera.lin',
    pnl: -42500,
    roi: -3.4,
    exposureType: 'Futures',
    strategies: [
      {
        id: 'strat-lin-01',
        name: 'Trend Ride FY25',
        symbol: 'NIFTY',
        timeframe: '5',
        metrics: {
          invested: 1260000,
          roi: -3.4,
          pnl: -42500,
          pop: 55.1,
          maxProfit: 210000,
          maxLoss: 250000,
          profitLeft: 165000,
          lossLeft: 208000,
        },
      },
    ],
  },
  {
    id: 'acct-rathi',
    username: 'veena.rathi',
    pnl: 62400,
    roi: 6.2,
    exposureType: 'Equity',
    strategies: [
      {
        id: 'strat-rathi-01',
        name: 'Covered Call Pulse',
        symbol: 'NIFTY',
        timeframe: '60',
        metrics: {
          invested: 680000,
          roi: 6.2,
          pnl: 62400,
          pop: 63.9,
          maxProfit: 94000,
          maxLoss: 120000,
          profitLeft: 31800,
          lossLeft: 102000,
        },
      },
    ],
  },
]

