"use client";

import { useEffect, useState, useCallback } from "react";
import { api, Account, Theme, WatchlistItem, Position, AlertItem } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null) return "—";
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}
function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  return (n * 100).toFixed(2) + "%";
}
function fmtUsd(n: number | null | undefined): string {
  if (n == null) return "—";
  return "$" + fmt(n);
}
function fmtVol(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(0) + "K";
  return n.toFixed(0);
}

const severityColor: Record<string, string> = {
  action: "bg-red-900/50 text-red-300 border-red-800",
  warning: "bg-yellow-900/50 text-yellow-300 border-yellow-800",
  info: "bg-blue-900/50 text-blue-300 border-blue-800",
  critical: "bg-red-700/50 text-red-200 border-red-600",
};
const statusColor: Record<string, string> = {
  hot: "bg-red-600",
  emerging: "bg-amber-600",
  cooling: "bg-blue-600",
  dead: "bg-neutral-600",
};

export default function Dashboard() {
  const [account, setAccount] = useState<Account | null>(null);
  const [themes, setThemes] = useState<Theme[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [pipelineResult, setPipelineResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [acc, th, wl, pos, al] = await Promise.allSettled([
        api.getAccount(),
        api.getThemes(),
        api.getWatchlist(),
        api.getPositions(),
        api.getAlerts(),
      ]);
      if (acc.status === "fulfilled") setAccount(acc.value);
      if (th.status === "fulfilled") setThemes(th.value);
      if (wl.status === "fulfilled") setWatchlist(wl.value);
      if (pos.status === "fulfilled") setPositions(pos.value);
      if (al.status === "fulfilled") setAlerts(al.value);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [refresh]);

  const runPipeline = async () => {
    setLoading(true);
    setPipelineResult(null);
    try {
      const result = await api.runFullPipeline();
      setPipelineResult(result);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  };

  const unreadAlerts = alerts.filter((a) => !a.acknowledged);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Newman Trading System</h1>
          <p className="text-neutral-400 text-sm mt-1">
            Sector-breakout strategy • Paper Trading
          </p>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" onClick={refresh} disabled={loading}>
            Refresh
          </Button>
          <Button onClick={runPipeline} disabled={loading} className="bg-green-700 hover:bg-green-600">
            {loading ? "Running..." : "▶ Run Pipeline"}
          </Button>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded-lg p-3 text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Account Overview */}
      {account && (
        <div className="grid grid-cols-5 gap-4">
          {[
            { label: "Portfolio", value: fmtUsd(account.portfolio_value) },
            { label: "Equity", value: fmtUsd(account.equity) },
            { label: "Cash", value: fmtUsd(account.cash) },
            { label: "Buying Power", value: fmtUsd(account.buying_power) },
            {
              label: "Daily P&L",
              value: fmtUsd(account.daily_pnl),
              color: account.daily_pnl >= 0 ? "text-green-400" : "text-red-400",
            },
          ].map((item) => (
            <Card key={item.label} className="bg-neutral-900 border-neutral-800">
              <CardContent className="pt-4 pb-3 px-4">
                <div className="text-xs text-neutral-400 uppercase tracking-wider">{item.label}</div>
                <div className={`text-xl font-semibold mt-1 ${item.color || ""}`}>{item.value}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Pipeline Result */}
      {pipelineResult && (
        <Card className="bg-neutral-900 border-neutral-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Pipeline Result</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-4 flex-wrap">
              {pipelineResult.steps?.map((step: any, i: number) => (
                <Badge key={i} variant="secondary" className="text-xs">
                  {step.step}: {JSON.stringify(Object.fromEntries(Object.entries(step).filter(([k]) => k !== "step")))}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Main Tabs */}
      <Tabs defaultValue="themes" className="w-full">
        <TabsList className="bg-neutral-900 border border-neutral-800">
          <TabsTrigger value="themes">🔥 Themes ({themes.length})</TabsTrigger>
          <TabsTrigger value="watchlist">📋 Watchlist ({watchlist.length})</TabsTrigger>
          <TabsTrigger value="positions">💼 Positions ({positions.length})</TabsTrigger>
          <TabsTrigger value="alerts">
            🔔 Alerts {unreadAlerts.length > 0 && `(${unreadAlerts.length})`}
          </TabsTrigger>
        </TabsList>

        {/* Themes Tab */}
        <TabsContent value="themes">
          <Card className="bg-neutral-900 border-neutral-800">
            <CardHeader>
              <CardTitle>Detected Themes</CardTitle>
              <CardDescription>Emerging sectors and catalysts scored by news, social, and ETF signals</CardDescription>
            </CardHeader>
            <CardContent>
              {themes.length === 0 ? (
                <p className="text-neutral-500 text-sm">No themes detected yet. Run the pipeline to scan.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="border-neutral-800">
                      <TableHead>Theme</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Score</TableHead>
                      <TableHead className="text-right">News</TableHead>
                      <TableHead className="text-right">Social</TableHead>
                      <TableHead className="text-right">ETF</TableHead>
                      <TableHead>Updated</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {themes.map((t) => (
                      <TableRow key={t.id} className="border-neutral-800">
                        <TableCell className="font-medium">{t.name}</TableCell>
                        <TableCell>
                          <Badge className={statusColor[t.status] || "bg-neutral-600"}>
                            {t.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-mono">{fmt(t.score)}</TableCell>
                        <TableCell className="text-right font-mono">{fmt(t.news_score)}</TableCell>
                        <TableCell className="text-right font-mono">{fmt(t.social_score)}</TableCell>
                        <TableCell className="text-right font-mono">{fmt(t.etf_score)}</TableCell>
                        <TableCell className="text-neutral-400 text-xs">
                          {t.updated_at ? new Date(t.updated_at).toLocaleString() : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Watchlist Tab */}
        <TabsContent value="watchlist">
          <Card className="bg-neutral-900 border-neutral-800">
            <CardHeader>
              <CardTitle>Watchlist</CardTitle>
              <CardDescription>Stocks passing theme + share structure filters</CardDescription>
            </CardHeader>
            <CardContent>
              {watchlist.length === 0 ? (
                <p className="text-neutral-500 text-sm">No watchlist items yet. Run the pipeline to build.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="border-neutral-800">
                      <TableHead>Symbol</TableHead>
                      <TableHead>Theme</TableHead>
                      <TableHead className="text-right">Price</TableHead>
                      <TableHead className="text-right">Avg Vol</TableHead>
                      <TableHead className="text-right">Float</TableHead>
                      <TableHead>Structure</TableHead>
                      <TableHead>Breakout</TableHead>
                      <TableHead className="text-right">Vol Ratio</TableHead>
                      <TableHead className="text-right">Rank</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {watchlist.map((w) => (
                      <TableRow key={w.id} className="border-neutral-800">
                        <TableCell className="font-bold">{w.symbol}</TableCell>
                        <TableCell className="text-xs text-neutral-400">{w.theme_name || "—"}</TableCell>
                        <TableCell className="text-right font-mono">{fmtUsd(w.price)}</TableCell>
                        <TableCell className="text-right font-mono">{fmtVol(w.avg_volume)}</TableCell>
                        <TableCell className="text-right font-mono">{fmtVol(w.float_shares)}</TableCell>
                        <TableCell>
                          <Badge variant={w.structure_clean ? "default" : "destructive"}>
                            {w.structure_clean ? "✓ Clean" : "✗ Fail"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {w.near_breakout ? (
                            <Badge className="bg-green-700">🚀 Near</Badge>
                          ) : (
                            <span className="text-neutral-500 text-xs">—</span>
                          )}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {w.volume_ratio ? `${w.volume_ratio.toFixed(1)}x` : "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono">{fmt(w.rank_score)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Positions Tab */}
        <TabsContent value="positions">
          <Card className="bg-neutral-900 border-neutral-800">
            <CardHeader>
              <CardTitle>Open Positions</CardTitle>
              <CardDescription>Active trades with P&L tracking</CardDescription>
            </CardHeader>
            <CardContent>
              {positions.length === 0 ? (
                <p className="text-neutral-500 text-sm">No open positions. The pipeline will enter trades on breakout signals.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="border-neutral-800">
                      <TableHead>Symbol</TableHead>
                      <TableHead className="text-right">Qty</TableHead>
                      <TableHead className="text-right">Entry</TableHead>
                      <TableHead className="text-right">Current</TableHead>
                      <TableHead className="text-right">P&L</TableHead>
                      <TableHead className="text-right">P&L %</TableHead>
                      <TableHead className="text-right">Value</TableHead>
                      <TableHead>Pyramid</TableHead>
                      <TableHead className="text-right">Stop</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {positions.map((p) => (
                      <TableRow key={p.id} className="border-neutral-800">
                        <TableCell className="font-bold">{p.symbol}</TableCell>
                        <TableCell className="text-right font-mono">{p.qty}</TableCell>
                        <TableCell className="text-right font-mono">{fmtUsd(p.avg_entry_price)}</TableCell>
                        <TableCell className="text-right font-mono">{fmtUsd(p.current_price)}</TableCell>
                        <TableCell
                          className={`text-right font-mono ${
                            p.unrealized_pnl >= 0 ? "text-green-400" : "text-red-400"
                          }`}
                        >
                          {fmtUsd(p.unrealized_pnl)}
                        </TableCell>
                        <TableCell
                          className={`text-right font-mono ${
                            p.unrealized_pnl_pct >= 0 ? "text-green-400" : "text-red-400"
                          }`}
                        >
                          {fmtPct(p.unrealized_pnl_pct)}
                        </TableCell>
                        <TableCell className="text-right font-mono">{fmtUsd(p.market_value)}</TableCell>
                        <TableCell>
                          <Badge variant="secondary">L{p.pyramid_level}</Badge>
                        </TableCell>
                        <TableCell className="text-right font-mono text-red-400">
                          {fmtUsd(p.stop_loss_price)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Alerts Tab */}
        <TabsContent value="alerts">
          <Card className="bg-neutral-900 border-neutral-800">
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Alerts</CardTitle>
                <CardDescription>Breakouts, entries, stops, and theme signals</CardDescription>
              </div>
              {unreadAlerts.length > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={async () => {
                    await api.ackAllAlerts();
                    refresh();
                  }}
                >
                  Mark All Read
                </Button>
              )}
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[500px]">
                {alerts.length === 0 ? (
                  <p className="text-neutral-500 text-sm">No alerts yet.</p>
                ) : (
                  <div className="space-y-3">
                    {alerts.map((a) => (
                      <div
                        key={a.id}
                        className={`rounded-lg border p-3 ${
                          severityColor[a.severity] || severityColor.info
                        } ${a.acknowledged ? "opacity-50" : ""}`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-sm">{a.title}</span>
                          <span className="text-xs opacity-70">
                            {a.created_at ? new Date(a.created_at).toLocaleString() : ""}
                          </span>
                        </div>
                        <p className="text-xs mt-1 whitespace-pre-wrap">{a.message}</p>
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
