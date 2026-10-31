import React from 'react'
import {
  ArrowLeft,
  BarChart3,
  Cpu,
  FileText,
} from 'lucide-react'
import type { IncidentRecord } from '../types/api'

interface IncidentDetailModalProps {
  incident: IncidentRecord | null
  onClose: () => void
}

export const IncidentDetailModal: React.FC<IncidentDetailModalProps> = ({
  incident,
  onClose,
}) => {
  if (!incident) return null

  const getSeverityBadge = (sev: string) => {
    switch (sev) {
      case 'CRITICAL':
        return 'bg-rose-500/20 text-rose-300 border-rose-500/40'
      case 'HIGH':
        return 'bg-amber-500/20 text-amber-300 border-amber-500/40'
      case 'MEDIUM':
        return 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
      default:
        return 'bg-slate-700/40 text-slate-300 border-slate-600'
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
      <div className="bg-[#0f172a] border border-slate-700/80 rounded-2xl max-w-3xl w-full p-6 sm:p-8 shadow-2xl relative space-y-6 my-auto">
        {/* Top bar */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm font-bold text-white">{incident.id}</span>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border font-bold ${getSeverityBadge(incident.severity)}`}>
                  {incident.severity}
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800">
                  DEMO SCENARIO
                </span>
              </div>
              <h2 className="text-lg font-bold text-slate-100 mt-1">{incident.incident_type}</h2>
            </div>
          </div>

          <div className="text-right text-xs">
            <div className="font-mono text-emerald-400 font-semibold">{incident.status}</div>
            <div className="text-slate-400 text-[11px] mt-0.5">Duration: {incident.duration_hours}h</div>
          </div>
        </div>

        {/* Root Cause & Diagnostic Overview */}
        <div className="space-y-4">
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-2">
              <FileText className="w-3.5 h-3.5 text-cyan-400" />
              Incident Summary & Root Cause
            </h4>
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 text-sm text-slate-200 leading-relaxed">
              {incident.description}
            </div>
          </div>

          {/* Diagnostic Evidence Cards */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-2">
              <Cpu className="w-3.5 h-3.5 text-purple-400" />
              Diagnostic Detection Evidence
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-3.5">
                <div className="text-[11px] text-slate-400">Verdict Classification</div>
                <div className="text-sm font-mono font-bold text-purple-300 mt-0.5">
                  {incident.verdict}
                </div>
                <div className="text-[11px] text-slate-400 mt-1">
                  Target DAG Layer: <span className="text-slate-200 font-mono">{incident.target_stage}</span>
                </div>
              </div>

              <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-3.5">
                <div className="text-[11px] text-slate-400">Injection Signature</div>
                <div className="text-xs font-mono text-cyan-300 mt-0.5 truncate">
                  {incident.diagnostic_details.injection || 'Synthetic failure'}
                </div>
                <div className="text-[11px] text-slate-400 mt-1">
                  Primary: {incident.diagnostic_details.primary_detector || 'Plumbline Engine'}
                </div>
              </div>
            </div>
          </div>

          {/* Top SPE Residual Contributors */}
          {incident.top_contributors && incident.top_contributors.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-2">
                <BarChart3 className="w-3.5 h-3.5 text-emerald-400" />
                Top SPE Residual Metric Contributors
              </h4>
              <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 space-y-3">
                {incident.top_contributors.map((contrib, idx) => (
                  <div key={idx} className="space-y-1">
                    <div className="flex items-center justify-between text-xs font-mono">
                      <span className="text-slate-300">{contrib.metric}</span>
                      <span className="text-emerald-400 font-semibold">{contrib.contribution_pct.toFixed(1)}%</span>
                    </div>
                    <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                      <div
                        className="bg-gradient-to-r from-cyan-500 to-emerald-400 h-full rounded-full transition-all"
                        style={{ width: `${Math.min(100, contrib.contribution_pct)}%` }}
                      ></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Affected Metrics Badge List */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
              Affected Business & Pipeline Metrics
            </h4>
            <div className="flex flex-wrap gap-2">
              {incident.affected_metrics.map((m) => (
                <span
                  key={m}
                  className="px-2.5 py-1 rounded-lg text-xs font-mono bg-slate-800/90 text-slate-200 border border-slate-700"
                >
                  {m}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="pt-4 border-t border-slate-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-xl text-xs font-semibold text-slate-200 transition-colors"
          >
            Close Incident Card
          </button>
        </div>
      </div>
    </div>
  )
}
