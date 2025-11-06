export type PositionStatus = 'Active' | 'Closed'
export type OrderStatus = 'Pending' | 'Filled' | 'Cancelled' | 'Partially Filled'

export interface OrderRow {
  id: string
  parentId: string | null
  symbol: string
  side: 'Buy' | 'Sell'
  quantity: number
  price: number
  status: OrderStatus
  type: 'Limit' | 'Market' | 'Stop'
  timestamp: string
}

export interface PositionRow {
  id: string
  symbol: string
  instrument: string
  quantity: number
  avgPrice: number
  ltp: number
  pnl: number
  roi: number
  status: PositionStatus
  orders: OrderRow[]
}

export interface HoldingRow {
  id: string
  symbol: string
  quantity: number
  avgPrice: number
  ltp: number
  pnl: number
  roi: number
  status: PositionStatus
  pledgedQuantity: number
  orders: OrderRow[]
}

export const DEFAULT_POSITIONS: PositionRow[] = [
  {
    id: 'pos-1',
    symbol: 'NIFTY24NOV17800CE',
    instrument: 'Options CE',
    quantity: 150,
    avgPrice: 52.4,
    ltp: 63.1,
    pnl: 1610,
    roi: 8.3,
    status: 'Active',
    orders: [
      {
        id: 'ord-1',
        parentId: 'pos-1',
        symbol: 'NIFTY24NOV17800CE',
        side: 'Sell',
        quantity: 75,
        price: 63,
        status: 'Filled',
        type: 'Limit',
        timestamp: '08 Nov 14:22',
      },
      {
        id: 'ord-2',
        parentId: 'pos-1',
        symbol: 'NIFTY24NOV17800CE',
        side: 'Sell',
        quantity: 75,
        price: 64,
        status: 'Pending',
        type: 'Limit',
        timestamp: '08 Nov 14:35',
      },
    ],
  },
  {
    id: 'pos-2',
    symbol: 'NIFTY24NOV17600PE',
    instrument: 'Options PE',
    quantity: -100,
    avgPrice: 68.5,
    ltp: 54.2,
    pnl: 1430,
    roi: 10.4,
    status: 'Active',
    orders: [
      {
        id: 'ord-3',
        parentId: 'pos-2',
        symbol: 'NIFTY24NOV17600PE',
        side: 'Buy',
        quantity: 50,
        price: 56,
        status: 'Partially Filled',
        type: 'Limit',
        timestamp: '08 Nov 13:48',
      },
      {
        id: 'ord-4',
        parentId: 'pos-2',
        symbol: 'NIFTY24NOV17600PE',
        side: 'Buy',
        quantity: 50,
        price: 52,
        status: 'Pending',
        type: 'Limit',
        timestamp: '08 Nov 13:51',
      },
    ],
  },
  {
    id: 'pos-3',
    symbol: 'NIFTY-I',
    instrument: 'Futures',
    quantity: 50,
    avgPrice: 21480,
    ltp: 21560,
    pnl: 4000,
    roi: 3.1,
    status: 'Closed',
    orders: [
      {
        id: 'ord-5',
        parentId: 'pos-3',
        symbol: 'NIFTY-I',
        side: 'Sell',
        quantity: 50,
        price: 21560,
        status: 'Filled',
        type: 'Market',
        timestamp: '08 Nov 12:05',
      },
    ],
  },
]

export const DEFAULT_HOLDINGS: HoldingRow[] = [
  {
    id: 'hold-1',
    symbol: 'HDFCBANK',
    quantity: 120,
    avgPrice: 1580,
    ltp: 1608,
    pnl: 3360,
    roi: 1.8,
    status: 'Active',
    pledgedQuantity: 0,
    orders: [
      {
        id: 'hold-ord-1',
        parentId: 'hold-1',
        symbol: 'HDFCBANK',
        side: 'Sell',
        quantity: 60,
        price: 1620,
        status: 'Pending',
        type: 'Limit',
        timestamp: '08 Nov 14:00',
      },
    ],
  },
  {
    id: 'hold-2',
    symbol: 'RELIANCE',
    quantity: 80,
    avgPrice: 2450,
    ltp: 2416,
    pnl: -2720,
    roi: -1.4,
    status: 'Active',
    pledgedQuantity: 40,
    orders: [],
  },
  {
    id: 'hold-3',
    symbol: 'INFY',
    quantity: 50,
    avgPrice: 1435,
    ltp: 1502,
    pnl: 3350,
    roi: 4.7,
    status: 'Closed',
    pledgedQuantity: 0,
    orders: [
      {
        id: 'hold-ord-2',
        parentId: 'hold-3',
        symbol: 'INFY',
        side: 'Sell',
        quantity: 50,
        price: 1500,
        status: 'Filled',
        type: 'Market',
        timestamp: '08 Nov 11:35',
      },
    ],
  },
]

export const DEFAULT_ORDERS: OrderRow[] = [
  {
    id: 'live-ord-1',
    parentId: null,
    symbol: 'NIFTY24NOV18000CE',
    side: 'Sell',
    quantity: 50,
    price: 33.5,
    status: 'Pending',
    type: 'Limit',
    timestamp: '08 Nov 14:42',
  },
  {
    id: 'live-ord-2',
    parentId: null,
    symbol: 'BANKNIFTY24NOV44500PE',
    side: 'Buy',
    quantity: 25,
    price: 82.1,
    status: 'Partially Filled',
    type: 'Limit',
    timestamp: '08 Nov 13:58',
  },
  {
    id: 'live-ord-3',
    parentId: null,
    symbol: 'RELIANCE',
    side: 'Sell',
    quantity: 20,
    price: 2445,
    status: 'Cancelled',
    type: 'Limit',
    timestamp: '08 Nov 13:02',
  },
  {
    id: 'live-ord-4',
    parentId: null,
    symbol: 'NIFTY-I',
    side: 'Buy',
    quantity: 50,
    price: 21510,
    status: 'Filled',
    type: 'Market',
    timestamp: '08 Nov 11:22',
  },
]

