import React, { useState } from 'react'
import {
  Clock,
  Layers,
  ChevronRight,
  Info,
} from 'lucide-react'
import type { IncidentRecord } from '../types/api'

interface AnomaliesViewProps {
  incidents: IncidentRecord[]
  loading: boolean
  error: string | null
  onSelectIncident: (inc: IncidentRecord) => void
}

export const AnomaliesView: React.FC<AnomaliesViewProps> = ({
  incidents,
  loading,
  error,
  onSelectIncident,
}) => {
  const [filterSeverity, setFilterSeverity] = useState<string>('ALL')

  if (loading) {
    return (
      <div className="p-8 text-center text-slate-400">
        <div className="animate-spin w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full mx-auto mb-3"></div>
        <p className="text-sm">Loading verified incident telemetry...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-rose-500/10 border border-rose-500/30 rounded-2xl p-6 text-rose-300">
          <h3 className="font-bold text-base mb-1">Failed to Load Incidents</h3>
          <p className="text-sm">{error}</p>
        </div>
      </div>
    )
  }

  const filtered = filterSeverity === 'ALL'
    ? incidents
    : incidents.filter((i) => i.severity === filterSeverity)

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

  const getVerdictBadge = (verdict: string) => {
    if (verdict === 'SOURCE_MISMATCH') {
      return 'bg-purple-500/20 text-purple-300 border-purple-500/40'
    }
    if (verdict === 'RELATIONSHIP_BREAK') {
      return 'bg-rose-500/20 text-rose-300 border-rose-500/40'
    }
    return 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
  }

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto">
      {/* Header & Filter Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-white">
              Anomaly & Incident Monitoring
            </h1>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800">
              DEMO SCENARIOS
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Verified detection output from Plumbline multi-group PCA and pre-injection control totals.
          </p>
        </div>

        {/* Severity Filter Tabs */}
        <div className="flex items-center gap-1.5 bg-slate-900/80 p-1 rounded-xl border border-slate-800 self-start sm:self-auto">
          {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM'].map((sev) => (
            <button
              key={sev}
              onClick={() => setFilterSeverity(sev)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                filterSeverity === sev
                  ? 'bg-slate-800 text-cyan-400 shadow-sm border border-slate-700'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {sev}
            </button>
          ))}
        </div>
      </div>

      {/* Synthetic Incident Transparency Notice */}
      <div className="bg-slate-900/40 border border-cyan-500/20 rounded-xl p-4 flex items-start gap-3">
        <Info className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
        <div className="text-xs text-slate-300 leading-relaxed">
          <span className="font-semibold text-cyan-300">Audited Evaluation Output:</span> The incidents listed below reflect deterministic failure injections executed and confirmed by Plumbline during benchmark and demo testing. Every scenario links back to verified ground truth records in DuckDB and SQLite.
        </div>
      </div>

      {/* Incident List */}
      <div className="space-y-3.5">
        {filtered.map((inc) => (
          <div
            key={inc.id}
            onClick={() => onSelectIncident(inc)}
            className="bg-slate-900/60 hover:bg-slate-800/50 backdrop-blur-md rounded-2xl p-5 border border-slate-800/80 hover:border-slate-700 transition-all cursor-pointer shadow-md group"
          >
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2.5">
                  <span className="font-mono text-xs font-bold text-slate-300">
                    {inc.id}
                  </span>
                  <span className={`text-[10px] font-mono px-2.5 py-0.5 rounded-full border font-bold ${getSeverityBadge(inc.severity)}`}>
                    {inc.severity}
                  </span>
                  <span className={`text-[10px] font-mono px-2.5 py-0.5 rounded-full border font-bold ${getVerdictBadge(inc.verdict)}`}>
                    {inc.verdict}
                  </span>
                  <span className="text-[10px] font-mono text-slate-400 flex items-center gap-1">
                    <Layers className="w-3 h-3 text-cyan-400" />
                    Stage: <span className="text-slate-200 font-semibold">{inc.target_stage}</span>
                  </span>
                </div>

                <h3 className="text-base font-semibold text-white group-hover:text-cyan-300 transition-colors">
                  {inc.description}
                </h3>

                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <span className="text-xs text-slate-400">Affected Metrics:</span>
                  {inc.affected_metrics.map((m) => (
                    <span
                      key={m}
                      className="text-[11px] font-mono bg-slate-800/80 text-slate-300 px-2 py-0.5 rounded border border-slate-700"
                    >
                      {m}
                    </span>
                  ))}
                </div>
              </div>

              {/* Action & Metadata */}
              <div className="flex items-center justify-between lg:justify-end gap-6 shrink-0 pt-3 lg:pt-0 border-t lg:border-t-0 border-slate-800">
                <div className="text-right">
                  <div className="text-xs font-mono text-slate-300">
                    Hour {inc.onset_hour}
                  </div>
                  <div className="text-[11px] text-slate-400 flex items-center gap-1 mt-0.5">
                    <Clock className="w-3 h-3" />
                    {inc.duration_hours}h duration
                  </div>
                </div>

                <div className="w-8 h-8 rounded-full bg-slate-800 group-hover:bg-cyan-500/20 group-hover:text-cyan-300 text-slate-400 flex items-center justify-center transition-all">
                  <ChevronRight className="w-4 h-4" />
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
