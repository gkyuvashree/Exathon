import React from 'react'
import {
  LayoutDashboard,
  AlertTriangle,
  LineChart,
  Network,
  Activity,
  
} from 'lucide-react'

export type TabId = 'overview' | 'anomalies' | 'explorer' | 'lineage'

interface SidebarProps {
  activeTab: TabId
  onSelectTab: (tab: TabId) => void
  pipelineStatus: string
  totalMetrics: number
  activeIncidents: number
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  
  totalMetrics,
  activeIncidents,
}) => {
  const navItems: Array<{ id: TabId; label: string; icon: React.ComponentType<{ className?: string }>; badge?: string | number }> = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'anomalies', label: 'Incidents & Anomalies', icon: AlertTriangle, badge: activeIncidents > 0 ? activeIncidents : undefined },
    { id: 'explorer', label: 'Metric Explorer', icon: LineChart, badge: totalMetrics > 0 ? totalMetrics : undefined },
    { id: 'lineage', label: 'Pipeline Lineage', icon: Network },
  ]

  return (
    <aside className="w-64 bg-[#0a0f1d] border-r border-slate-800 flex flex-col justify-between shrink-0 select-none">
      <div>
        {/* Brand */}
        <div className="h-16 flex items-center px-6 border-b border-slate-800 gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-cyan-500 via-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
            <Activity className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="text-sm font-bold tracking-wider text-slate-100 flex items-center gap-1.5">
              EXATHON
              <span className="text-[10px] px-1.5 py-0.2 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/60 font-mono">
                v0.2
              </span>
            </div>
            <div className="text-[11px] text-slate-400">Observability Platform</div>
          </div>
        </div>

        {/* Navigation */}
        <div className="p-4 space-y-1.5">
          <div className="px-3 pb-2 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Telemetry & Control
          </div>
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = activeTab === item.id
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  isActive
                    ? 'bg-gradient-to-r from-cyan-500/10 via-purple-500/10 to-transparent text-cyan-400 border-l-2 border-cyan-400 font-semibold shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-cyan-400' : 'text-slate-400'}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge !== undefined && (
                  <span
                    className={`text-[11px] px-2 py-0.5 rounded-full font-mono ${
                      item.id === 'anomalies'
                        ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                        : 'bg-slate-800 text-slate-300 border border-slate-700'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* System Status Footprint */}
      <div className="p-4 border-t border-slate-800/80 bg-slate-900/40">
        <div className="bg-slate-950/60 rounded-xl p-3 border border-slate-800/80">
          <div className="flex items-center justify-between text-xs mb-2">
            <span className="text-slate-400 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              DuckDB Engine
            </span>
            <span className="text-[11px] font-mono text-emerald-400 font-medium">ONLINE</span>
          </div>
          <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-800">
            <span>Coherence Model</span>
            <span className="font-mono text-cyan-400">Plumbline PCA</span>
          </div>
        </div>
      </div>
    </aside>
  )
}
