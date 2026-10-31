import { useEffect, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Activity,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Server,
  Layers,
  BarChart3,
  Terminal,
} from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

interface HealthResponse {
  status: string
  service: string
  version: string
  timestamp: string
}

interface LatencyPoint {
  time: string
  latencyMs: number
}

// Sample lineage DAG nodes for pipeline preview verification
const initialNodes: Node[] = [
  {
    id: '1',
    position: { x: 50, y: 30 },
    data: { label: 'raw_orders' },
    style: {
      background: '#1e293b',
      color: '#38bdf8',
      border: '1px solid #38bdf8',
      borderRadius: '8px',
      fontSize: '12px',
      padding: '8px 12px',
    },
  },
  {
    id: '2',
    position: { x: 230, y: 30 },
    data: { label: 'stg_orders' },
    style: {
      background: '#1e293b',
      color: '#a855f7',
      border: '1px solid #a855f7',
      borderRadius: '8px',
      fontSize: '12px',
      padding: '8px 12px',
    },
  },
  {
    id: '3',
    position: { x: 410, y: 30 },
    data: { label: 'int_order_totals' },
    style: {
      background: '#1e293b',
      color: '#10b981',
      border: '1px solid #10b981',
      borderRadius: '8px',
      fontSize: '12px',
      padding: '8px 12px',
    },
  },
  {
    id: '4',
    position: { x: 610, y: 30 },
    data: { label: 'mart_revenue' },
    style: {
      background: '#1e293b',
      color: '#f59e0b',
      border: '1px solid #f59e0b',
      borderRadius: '8px',
      fontSize: '12px',
      padding: '8px 12px',
    },
  },
]

const initialEdges: Edge[] = [
  { id: 'e1-2', source: '1', target: '2', animated: true, style: { stroke: '#38bdf8' } },
  { id: 'e2-3', source: '2', target: '3', animated: true, style: { stroke: '#a855f7' } },
  { id: 'e3-4', source: '3', target: '4', animated: true, style: { stroke: '#10b981' } },
]

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [latencyHistory, setLatencyHistory] = useState<LatencyPoint[]>([])
  const [lastChecked, setLastChecked] = useState<Date | null>(null)

  const fetchHealth = useCallback(async () => {
    setLoading(true)
    setError(null)
    const startTime = performance.now()
    try {
      const res = await fetch('/api/health')
      const elapsed = Math.round(performance.now() - startTime)
      if (!res.ok) {
        throw new Error(`HTTP error ${res.status}: ${res.statusText}`)
      }
      const data: HealthResponse = await res.json()
      setHealth(data)
      setLastChecked(new Date())

      const nowStr = new Date().toLocaleTimeString()
      setLatencyHistory((prev) => [
        ...prev.slice(-9),
        { time: nowStr, latencyMs: elapsed },
      ])
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to reach /api/health'
      setError(message)
      setHealth(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchHealth()
  }, [fetchHealth])

  const isHealthy = health?.status === 'healthy'

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Navigation */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-indigo-500/10 border border-indigo-500/30 rounded-lg">
              <Activity className="w-5 h-5 text-indigo-400" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
                EXATHON
                <span className="text-xs font-mono font-normal px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
                  Phase 0 Scaffold
                </span>
              </h1>
              <p className="text-xs text-slate-400">Data Pipeline & Observability Engine</p>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            <button
              onClick={fetchHealth}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              Recheck Health
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-8 space-y-8">
        {/* Status Card Hero */}
        <section>
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className={`p-6 rounded-2xl border transition-all ${
              isHealthy
                ? 'bg-emerald-950/20 border-emerald-500/30 shadow-lg shadow-emerald-950/20'
                : error
                ? 'bg-rose-950/20 border-rose-500/30 shadow-lg shadow-rose-950/20'
                : 'bg-slate-900/50 border-slate-800'
            }`}
          >
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div
                  className={`p-3 rounded-xl border ${
                    isHealthy
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                      : error
                      ? 'bg-rose-500/10 border-rose-500/30 text-rose-400'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`}
                >
                  {isHealthy ? (
                    <CheckCircle2 className="w-8 h-8" />
                  ) : error ? (
                    <AlertCircle className="w-8 h-8" />
                  ) : (
                    <Server className="w-8 h-8 animate-pulse" />
                  )}
                </div>

                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-xl font-bold tracking-tight text-white">
                      Backend Status:{' '}
                      <span
                        className={
                          isHealthy
                            ? 'text-emerald-400'
                            : error
                            ? 'text-rose-400'
                            : 'text-slate-400'
                        }
                      >
                        {loading && !health
                          ? 'Checking...'
                          : isHealthy
                          ? 'HEALTHY'
                          : error
                          ? 'OFFLINE / ERROR'
                          : 'UNKNOWN'}
                      </span>
                    </h2>
                    <span
                      className={`inline-block w-2.5 h-2.5 rounded-full ${
                        isHealthy
                          ? 'bg-emerald-400 animate-ping'
                          : error
                          ? 'bg-rose-400'
                          : 'bg-slate-500'
                      }`}
                    />
                  </div>
                  <p className="text-xs text-slate-400 mt-1">
                    Endpoint: <code className="text-slate-300">GET /api/health</code> via Vite
                    proxy (:5173/api -&gt; :8000)
                  </p>
                </div>
              </div>

              {lastChecked && (
                <div className="text-right text-xs text-slate-400 font-mono">
                  Last checked: {lastChecked.toLocaleTimeString()}
                </div>
              )}
            </div>

            {/* Error banner if offline */}
            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mt-4 p-4 rounded-xl bg-rose-950/40 border border-rose-800/40 text-xs text-rose-300 font-mono"
                >
                  <p className="font-semibold text-rose-200">Connection Failed:</p>
                  <p>{error}</p>
                  <p className="mt-2 text-rose-400">
                    Ensure FastAPI backend is running on port 8000 (<code>uvicorn app.main:app --port 8000</code>).
                  </p>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Health Payload details */}
            {health && (
              <div className="mt-6 pt-6 border-t border-slate-800/80 grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
                    Service
                  </div>
                  <div className="text-sm font-semibold text-white mt-0.5">{health.service}</div>
                </div>
                <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
                    Version
                  </div>
                  <div className="text-sm font-mono text-indigo-400 mt-0.5">v{health.version}</div>
                </div>
                <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
                    Status Code
                  </div>
                  <div className="text-sm font-mono text-emerald-400 mt-0.5">200 OK</div>
                </div>
                <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
                    Server Timestamp
                  </div>
                  <div className="text-xs font-mono text-slate-300 mt-1 truncate" title={health.timestamp}>
                    {new Date(health.timestamp).toLocaleTimeString()}
                  </div>
                </div>
              </div>
            )}
          </motion.div>
        </section>

        {/* Diagnostic Grid: Latency Chart & Raw Response */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Latency History Chart (Recharts verification) */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.1 }}
            className="p-5 rounded-xl border border-slate-800 bg-slate-900/40 flex flex-col justify-between"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-sky-400" />
                <h3 className="text-sm font-semibold text-white">API Health Latency</h3>
              </div>
              <span className="text-xs text-slate-400 font-mono">Recharts Engine</span>
            </div>

            <div className="h-44 w-full">
              {latencyHistory.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={latencyHistory}>
                    <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickLine={false} />
                    <YAxis
                      stroke="#64748b"
                      fontSize={10}
                      tickLine={false}
                      unit="ms"
                      width={35}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0f172a',
                        borderColor: '#334155',
                        borderRadius: '6px',
                        fontSize: '12px',
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="latencyMs"
                      stroke="#38bdf8"
                      strokeWidth={2}
                      dot={{ fill: '#38bdf8', r: 3 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-xs text-slate-500">
                  Click 'Recheck Health' to record latency samples.
                </div>
              )}
            </div>
          </motion.div>

          {/* Raw JSON Response */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.15 }}
            className="p-5 rounded-xl border border-slate-800 bg-slate-900/40 flex flex-col justify-between"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-emerald-400" />
                <h3 className="text-sm font-semibold text-white">Live /api/health Payload</h3>
              </div>
              <span className="text-xs font-mono text-slate-400">application/json</span>
            </div>

            <pre className="p-3 rounded-lg bg-slate-950 border border-slate-800/80 text-xs font-mono text-emerald-300 overflow-x-auto h-44">
              {health
                ? JSON.stringify(health, null, 2)
                : error
                ? JSON.stringify({ error }, null, 2)
                : '// Waiting for response...'}
            </pre>
          </motion.div>
        </div>

        {/* Pipeline Lineage Preview (@xyflow/react verification) */}
        <motion.section
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.2 }}
          className="p-5 rounded-xl border border-slate-800 bg-slate-900/40"
        >
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-indigo-400" />
              <h3 className="text-sm font-semibold text-white">
                Pipeline DAG Preview (XYFlow Lineage Engine)
              </h3>
            </div>
            <span className="text-xs text-slate-400">@xyflow/react Ready</span>
          </div>

          <div className="h-44 w-full rounded-lg overflow-hidden border border-slate-800 bg-slate-950">
            <ReactFlow
              nodes={initialNodes}
              edges={initialEdges}
              fitView
              zoomOnScroll={false}
              panOnDrag={false}
              proOptions={{ hideAttribution: true }}
            >
              <Background color="#1e293b" gap={16} />
              <Controls position="bottom-right" showInteractive={false} />
            </ReactFlow>
          </div>
        </motion.section>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/60 py-4 text-center text-xs text-slate-500">
        Exathon Scaffold • Vite + React + TypeScript + Tailwind v3.4 + FastAPI
      </footer>
    </div>
  )
}
