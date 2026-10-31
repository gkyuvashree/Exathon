import React from 'react'
import {
  Activity,
  DollarSign,
  ShoppingCart,
  ShieldAlert,
  Clock,
  TrendingUp,
  RefreshCw,
} from 'lucide-react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
} from 'recharts'
import type { OverviewData } from '../types/api'

interface OverviewViewProps {
  data: OverviewData | null
  loading: boolean
  error: string | null
  onRefresh: () => void
  onNavigateToIncidents: () => void
}

export const OverviewView: React.FC<OverviewViewProps> = ({
  data,
  loading,
  error,
  onRefresh,
  onNavigateToIncidents,
}) => {
  if (loading && !data) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-slate-400">
          <RefreshCw className="w-8 h-8 animate-spin text-cyan-400" />
          <p className="text-sm font-medium">Fetching telemetry overview...</p>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="p-8">
        <div className="bg-rose-500/10 border border-rose-500/30 rounded-2xl p-6 text-rose-300">
          <h3 className="font-bold text-lg mb-1">Failed to Load Overview</h3>
          <p className="text-sm text-rose-400">{error || 'Data could not be retrieved from backend.'}</p>
          <button
            onClick={onRefresh}
            className="mt-4 px-4 py-2 bg-rose-500/20 hover:bg-rose-500/30 rounded-lg text-xs font-semibold"
          >
            Retry Connection
          </button>
        </div>
      </div>
    )
  }

  // Format revenue
  const formattedRev = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(data.last_24h_revenue)

  // Chart data formatting
  const chartData = data.hourly_trends_24h.map((pt) => {
    const dt = new Date(pt.timestamp)
    const timeStr = dt.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
    return {
      ...pt,
      timeLabel: timeStr,
    }
  })

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
            System Observability Overview
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              {data.pipeline_status}
            </span>
          </h1>
          <p className="text-sm text-slate-400 mt-1 flex items-center gap-2">
            <Clock className="w-3.5 h-3.5" />
            Historical horizon up to hour <span className="font-mono text-slate-300 font-semibold">{data.latest_hour}</span> ({new Date(data.latest_timestamp).toUTCString()})
          </p>
        </div>

        <button
          onClick={onRefresh}
          className="self-start md:self-auto flex items-center gap-2 px-3.5 py-2 bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700 rounded-xl text-xs font-medium text-slate-200 transition-all shadow-sm"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
          Refresh Live Status
        </button>
      </div>

      {/* KPI Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: 24h Revenue */}
        <div className="bg-slate-900/60 backdrop-blur-md rounded-2xl p-5 border border-slate-800/80 shadow-lg relative overflow-hidden">
          <div className="flex items-center justify-between text-slate-400 mb-3">
            <span className="text-xs font-semibold uppercase tracking-wider">24h Pipeline Revenue</span>
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
              <DollarSign className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">{formattedRev}</div>
          <div className="text-[12px] text-emerald-400/90 mt-2 flex items-center gap-1">
            <TrendingUp className="w-3.5 h-3.5" />
            Continuous multi-tier mart rollup
          </div>
        </div>

        {/* Card 2: 24h Orders */}
        <div className="bg-slate-900/60 backdrop-blur-md rounded-2xl p-5 border border-slate-800/80 shadow-lg relative overflow-hidden">
          <div className="flex items-center justify-between text-slate-400 mb-3">
            <span className="text-xs font-semibold uppercase tracking-wider">24h Order Volume</span>
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 text-cyan-400 flex items-center justify-center">
              <ShoppingCart className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight font-mono">
            {data.last_24h_orders.toLocaleString()}
          </div>
          <div className="text-[12px] text-slate-400 mt-2">
            Average ~{Math.round(data.last_24h_orders / 24)} orders/hour
          </div>
        </div>

        {/* Card 3: Monitored Metrics */}
        <div className="bg-slate-900/60 backdrop-blur-md rounded-2xl p-5 border border-slate-800/80 shadow-lg relative overflow-hidden">
          <div className="flex items-center justify-between text-slate-400 mb-3">
            <span className="text-xs font-semibold uppercase tracking-wider">Monitored Metrics</span>
            <div className="w-8 h-8 rounded-lg bg-purple-500/10 text-purple-400 flex items-center justify-center">
              <Activity className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight font-mono">
            {data.total_monitored_metrics}
          </div>
          <div className="text-[12px] text-purple-400 mt-2">
            5 groups across 5 pipeline DAG tiers
          </div>
        </div>

        {/* Card 4: Active Incidents */}
        <div
          onClick={onNavigateToIncidents}
          className="bg-slate-900/60 backdrop-blur-md rounded-2xl p-5 border border-slate-800/80 shadow-lg cursor-pointer hover:border-slate-700 transition-all group"
        >
          <div className="flex items-center justify-between text-slate-400 mb-3">
            <span className="text-xs font-semibold uppercase tracking-wider">Verified Demo Scenarios</span>
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 text-cyan-400 flex items-center justify-center group-hover:scale-105 transition-transform">
              <ShieldAlert className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight font-mono flex items-center gap-2">
            3 Ready
            <span className="text-[10px] font-sans px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
              AUDITED
            </span>
          </div>
          <div className="text-[12px] text-cyan-400 group-hover:underline mt-2">
            Inspect root causes & diagnostic cards &rarr;
          </div>
        </div>
      </div>

      {/* Main Trends: Revenue & Orders Side by Side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Revenue Hourly Area Chart */}
        <div className="bg-slate-900/60 backdrop-blur-md rounded-2xl p-6 border border-slate-800/80 shadow-lg">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-base font-bold text-white">Trailing 24h Revenue Trend</h3>
              <p className="text-xs text-slate-400">Hourly aggregation from mart_revenue_hourly</p>
            </div>
            <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-md border border-emerald-500/20 font-medium">
              mart_hourly_revenue
            </span>
          </div>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="revGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="timeLabel" stroke="#64748b" fontSize={11} tickLine={false} />
                <YAxis
                  stroke="#64748b"
                  fontSize={11}
                  tickLine={false}
                  tickFormatter={(v) => `$${Math.round(v / 1000)}k`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                    fontSize: '12px',
                    color: '#f8fafc',
                  }}
                  formatter={(val: number) => [`$${val.toLocaleString()}`, 'Revenue']}
                  labelFormatter={(lbl) => `Time: ${lbl}`}
                />
                <Area
                  type="monotone"
                  dataKey="revenue"
                  stroke="#10b981"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#revGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Order Count Hourly Bar Chart */}
        <div className="bg-slate-900/60 backdrop-blur-md rounded-2xl p-6 border border-slate-800/80 shadow-lg">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-base font-bold text-white">Trailing 24h Order Throughput</h3>
              <p className="text-xs text-slate-400">Total orders landed per hourly pipeline batch</p>
            </div>
            <span className="text-xs font-mono text-cyan-400 bg-cyan-500/10 px-2.5 py-1 rounded-md border border-cyan-500/20 font-medium">
              mart_order_count
            </span>
          </div>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <XAxis dataKey="timeLabel" stroke="#64748b" fontSize={11} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={11} tickLine={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                    fontSize: '12px',
                    color: '#f8fafc',
                  }}
                  formatter={(val: number) => [val.toLocaleString(), 'Orders']}
                  labelFormatter={(lbl) => `Time: ${lbl}`}
                />
                <Bar dataKey="orders" fill="#06b6d4" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  )
}
