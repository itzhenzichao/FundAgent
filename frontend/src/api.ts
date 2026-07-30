import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export interface FundInfo {
  code: string
  name: string
  type: string
  latest_nav: number | null
  latest_date: string | null
  nav_history: { date: string; nav: number }[]
}

export interface Holding {
  stock_code: string
  stock_name: string
  holding_ratio: number | null
  holding_amount: number | null
  holding_value: number | null
  quarter: string
}

export interface IndustryItem {
  industry: string
  stocks: { stock_code: string; stock_name: string; holding_ratio: number | null }[]
  total_ratio: number
}

export interface Deviation {
  claimed_industry: string
  claimed_ratio: number
  threshold: number
  is_deviant: boolean
}

export interface FundIndustryResult {
  fund_code: string
  fund_name: string
  quarter: string
  industry_distribution: IndustryItem[]
  unmatched_stocks: { stock_code: string; stock_name: string; holding_ratio: number | null }[]
  deviation: Deviation | null
  total_count: number
  truncated: boolean
}

export const searchFund = (code: string) =>
  api.get<FundInfo>('/fund/search', { params: { code } }).then(r => r.data)

export const getHoldings = (code: string, date?: string) =>
  api.get<{ fund_code: string; holdings: Holding[]; quarter: string; total_count: number; truncated: boolean }>('/fund/holdings', { params: { code, date } }).then(r => r.data)

export const getFundIndustry = (code: string, date?: string, fundName?: string) =>
  api.get<FundIndustryResult>('/fund/industry', { params: { code, date, fund_name: fundName } }).then(r => r.data)

export interface WatchlistItem {
  code: string
  name: string
  added_at: string
  position_amount: number
  balance: number | null
  profit: number | null
  profit_rate: number | null
  is_holding: boolean
}

export const addWatchlist = (code: string, name: string) =>
  api.post('/watchlist/add', { code, name }).then(r => r.data)

export const removeWatchlist = (code: string) =>
  api.delete('/watchlist/remove', { params: { code } }).then(r => r.data)

export const getWatchlist = () =>
  api.get<WatchlistItem[]>('/watchlist/list').then(r => r.data)

export const updatePosition = (code: string, position_amount: number, profit: number) =>
  api.put('/watchlist/position', { code, position_amount, profit }).then(r => r.data)

export interface NavData {
  fund_code: string
  period: string
  nav_data: { date: string; nav: number }[]
  drawdown_data: { date: string; drawdown: number }[]
  max_drawdown: number
}

export const getFundNav = (code: string, period: string = '1y') =>
  api.get<NavData>('/fund/nav', { params: { code, period } }).then(r => r.data)

export interface ReturnsData {
  fund_code: string
  returns: { date: string; nav: number; daily_return: number }[]
}

export const getFundReturns = (code: string) =>
  api.get<ReturnsData>('/fund/returns', { params: { code } }).then(r => r.data)

export interface BondHoldingData {
  fund_code: string
  bond_holdings: { bond_code: string; bond_name: string; holding_ratio: number | null; holding_value: number | null; quarter: string }[]
  quarter: string
  total_count: number
  truncated: boolean
}

export const getBondHoldings = (code: string) =>
  api.get<BondHoldingData>('/fund/bond-holdings', { params: { code } }).then(r => r.data)
