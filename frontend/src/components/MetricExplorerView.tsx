import React, { useState, useEffect } from 'react'
import {
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import {
  Layers,
  RefreshCw,
} from 'lucide-react'
import type { MetricCatalogData, TimeseriesData } from '../types/api'
import { fetchTimeseries } from '../api/client'

interface MetricExplorerViewProps {
  catalog: MetricCatalogData | null
  loadingCatalog: boolean
}

export const MetricExplorerView: React.FC<MetricExplorerViewProps> = ({
  catalog,
  loadingCatalog: _loadingCatalog,
}) => {
  const [selectedGroup, setSelectedGroup] = useState<string>('mart')
  const [selectedMetric, setSelectedMetric] = useState<string>('mart_hourly_revenue')
  const [selectedSegment, setSelectedSegment] = useState<string>('ALL')
  const [timeRangeHours, setTimeRangeHours] = useState<number>(72) // Last 72 hours
  const [seriesData, setSeriesData] = useState<TimeseriesData | null>(null)
  const [loadingSeries, setLoadingSeries] = useState<boolean>(false)
  const [errorSeries, setErrorSeries] = useState<string | null>(null)

  // Segment options based on group
  const getSegmentOptions = (group: string) => {
    switch (group) {
      case 'orders':
        return ['ALL', 'CA', 'NY', 'TX', 'FL', 'IL', 'PA', 'OH', 'WA']
      case 'items':
        return ['ALL', 'electronics', 'apparel', 'home_kitchen', 'beauty', 'books', 'sports']
      case 'payments':
        return ['ALL', 'credit_card', 'debit_card', 'voucher', 'wallet']
      default:
        return ['ALL']
    }
  }

  // Fetch timeseries when selection changes
  useEffect(() => {
    let isCancelled = false
    async function loadData() {
      if (!selectedMetric) return
      setLoadingSeries(true)
      setErrorSeries(null)
      try {
        const endHour = 2879 // latest available in metrics.db
        const startHour = Math.max(0, endHour - timeRangeHours)
        const res = await fetchTimeseries(selectedMetric, selectedSegment, startHour, endHour)
        if (!isCancelled) {
          setSeriesData(res)
        }
      } catch (err: any) {
        if (!isCancelled) {
          setErrorSeries(err.message || 'Failed to load metric data')
        }
      } finally {
        if (!isCancelled) {
          setLoadingSeries(false)
        }
      }
    }

    loadData()
    return () => {
      isCancelled = true
    }
  }, [selectedMetric, selectedSegment, timeRangeHours])

  const groupMetrics = catalog?.groups.find((g) => g.group === selectedGroup)?.metrics || []
  const segmentOptions = getSegmentOptions(selectedGroup)

  const chartPoints = seriesData?.data.map((pt) => {
    const dt = new Date(pt.timestamp)
    const timeStr = `${dt.getMonth() + 1}/${dt.getDate()} ${dt.getHours()}:00`
    return {
      hour_ts: pt.hour_ts,
      timeLabel: timeStr,
      value: pt.value,
    }
  }) || []

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
          Metric Explorer
          <span className="text-xs font-mono px-2.5 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800">
            DuckDB Vectorized Storage
          </span>
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Interactive time-series query interface across 120-day historical pipeline metrics and segmented slices.
        </p>
      </div>

      {/* Control Panel: Group, Metric, Segment, Horizon */}
      <div className="bg-slate-900/60 backdrop-blur-md rounded-2xl p-5 border border-slate-800 shadow-lg space-y-4">
        {/* Metric Group Tabs */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase text-slate-400 mr-2 flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-cyan-400" />
            Group:
          </span>
          {catalog?.groups.map((grp) => (
            <button
              key={grp.group}
              onClick={() => {
                setSelectedGroup(grp.group)
                if (grp.metrics.length > 0) {
                  setSelectedMetric(grp.metrics[0].name)
                }
                setSelectedSegment('ALL')
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium font-mono transition-all ${
                selectedGroup === grp.group
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                  : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 border border-slate-700/60'
              }`}
            >
              {grp.group} ({grp.metric_count})
            </button>
          ))}
        </div>

        {/* Metric and Segment Selectors */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2 border-t border-slate-800/60">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Select Metric
            </label>
            <select
              value={selectedMetric}
              onChange={(e) => setSelectedMetric(e.target.value)}
              className="w-full bg-slate-800/90 border border-slate-700 rounded-xl px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-400"
            >
              {groupMetrics.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name} ({m.kind})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Slice / Segment Dimension
            </label>
            <select
              value={selectedSegment}
              onChange={(e) => setSelectedSegment(e.target.value)}
              className="w-full bg-slate-800/90 border border-slate-700 rounded-xl px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-400"
            >
              {segmentOptions.map((seg) => (
                <option key={seg} value={seg}>
                  segment: {seg}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Time Horizon Range
            </label>
            <div className="flex gap-2">
              {[24, 72, 168, 720].map((hours) => (
                <button
                  key={hours}
                  onClick={() => setTimeRangeHours(hours)}
                  className={`flex-1 py-2 rounded-xl text-xs font-mono font-medium border transition-all ${
                    timeRangeHours === hours
                      ? 'bg-purple-500/20 text-purple-300 border-purple-500/40'
                      : 'bg-slate-800/60 text-slate-400 border-slate-700/60 hover:text-slate-200'
                  }`}
                >
                  {hours === 168 ? '7d' : hours === 720 ? '30d' : `${hours}h`}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="bg-slate-900/60 backdrop-blur-md rounded-2xl p-6 border border-slate-800 shadow-lg space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <span className="font-mono text-cyan-400">{selectedMetric}</span>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                segment: {selectedSegment}
              </span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              {seriesData?.count ? `${seriesData.count} data points retrieved from SQLite metrics_ts` : 'Loading series...'}
            </p>
          </div>

          <div className="text-xs font-mono text-slate-400">
            Node: <span className="text-slate-200 font-semibold">{seriesData?.node || '...'}</span>
          </div>
        </div>

        {loadingSeries ? (
          <div className="h-80 flex items-center justify-center text-slate-400">
            <RefreshCw className="w-6 h-6 animate-spin text-cyan-400 mr-2" />
            <span className="text-xs">Querying time series...</span>
          </div>
        ) : errorSeries ? (
          <div className="h-80 flex items-center justify-center text-rose-400 text-sm">
            {errorSeries}
          </div>
        ) : chartPoints.length === 0 ? (
          <div className="h-80 flex items-center justify-center text-slate-400 text-sm">
            No metric data found for this segment in the selected range.
          </div>
        ) : (
          <div className="h-80 w-full pt-4">
            <ResponsiveContainer width="100%" height="100%">
              <RechartsLineChart data={chartPoints} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  dataKey="timeLabel"
                  stroke="#64748b"
                  fontSize={11}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  stroke="#64748b"
                  fontSize={11}
                  tickLine={false}
                  tickFormatter={(val) => (val >= 1000 ? `${(val / 1000).toFixed(1)}k` : val.toFixed(1))}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                    fontSize: '12px',
                    color: '#f8fafc',
                  }}
                  formatter={(val: number) => [val.toLocaleString(), selectedMetric]}
                  labelFormatter={(lbl) => `Time: ${lbl}`}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#38bdf8"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 5, fill: '#38bdf8' }}
                />
              </RechartsLineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}
