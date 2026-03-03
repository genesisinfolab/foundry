const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let _authToken: string | null = null;

export function setAuthToken(token: string | null) {
  _authToken = token;
}

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(_authToken ? { Authorization: `Bearer ${_authToken}` } : {}),
      ...options?.headers,
    },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// Types
export interface Theme {
  id: number;
  name: string;
  status: string;
  score: number;
  news_score: number;
  social_score: number;
  etf_score: number;
  keywords: string | null;
  related_etfs: string | null;
  created_at: string;
  updated_at: string;
}

export interface WatchlistItem {
  id: number;
  symbol: string;
  company_name: string | null;
  theme_id: number | null;
  theme_name: string | null;
  price: number | null;
  avg_volume: number | null;
  float_shares: number | null;
  market_cap: number | null;
  structure_clean: boolean;
  structure_notes: string | null;
  near_breakout: boolean;
  volume_ratio: number | null;
  rank_score: number;
  catalyst_type: string | null;
  catalyst_date: string | null;
}

export interface Position {
  id: number;
  symbol: string;
  theme_id: number | null;
  status: string;
  qty: number;
  avg_entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  realized_pnl: number;
  pyramid_level: number;
  stop_loss_price: number | null;
  opened_at: string;
  closed_at: string | null;
  actions: { type: string; qty: number; price: number; reason: string; at: string }[];
}

export interface AlertItem {
  id: number;
  type: string;
  symbol: string | null;
  theme_name: string | null;
  title: string;
  message: string;
  severity: string;
  acknowledged: boolean;
  created_at: string;
}

export interface Account {
  equity: number;
  cash: number;
  buying_power: number;
  portfolio_value: number;
  daily_pnl: number;
}

export interface PipelineResult {
  steps: { step: string; [key: string]: any }[];
  summary: any;
}

// API calls
export const api = {
  // Auth
  setAuthToken,

  // Account
  getAccount: () => fetchApi<Account>("/api/account"),

  // Themes
  getThemes: () => fetchApi<Theme[]>("/api/themes/"),
  getTheme: (id: number) => fetchApi<any>(`/api/themes/${id}`),
  triggerScan: () => fetchApi<any>("/api/themes/scan", { method: "POST" }),

  // Watchlist
  getWatchlist: (cleanOnly = false) =>
    fetchApi<WatchlistItem[]>(`/api/watchlist/?clean_only=${cleanOnly}`),
  buildWatchlist: (themeId: number) =>
    fetchApi<any>(`/api/watchlist/build/${themeId}`, { method: "POST" }),
  checkStructure: () => fetchApi<any>("/api/watchlist/check-structure", { method: "POST" }),

  // Positions
  getPositions: (status = "open") =>
    fetchApi<Position[]>(`/api/positions/?status=${status}`),
  getPortfolioSummary: () => fetchApi<any>("/api/positions/summary"),

  // Alerts
  getAlerts: (limit = 50) => fetchApi<AlertItem[]>(`/api/alerts/?limit=${limit}`),
  ackAlert: (id: number) => fetchApi<any>(`/api/alerts/${id}/ack`, { method: "POST" }),
  ackAllAlerts: () => fetchApi<any>("/api/alerts/ack-all", { method: "POST" }),

  // Pipeline
  runFullPipeline: () => fetchApi<PipelineResult>("/api/pipeline/run-full", { method: "POST" }),
};
