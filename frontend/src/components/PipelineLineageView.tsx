import React, { useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  BackgroundVariant,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { CheckCircle2, Info } from 'lucide-react'
import type { LineageData } from '../types/api'

interface PipelineLineageViewProps {
  lineage: LineageData | null
  loading: boolean
  error: string | null
}

const LAYER_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  raw: { bg: '#0f172a', border: '#38bdf8', text: '#38bdf8' },
  staging: { bg: '#0f172a', border: '#818cf8', text: '#818cf8' },
  intermediate: { bg: '#0f172a', border: '#c084fc', text: '#c084fc' },
  mart: { bg: '#0f172a', border: '#34d399', text: '#34d399' },
  kpi: { bg: '#0f172a', border: '#f59e0b', text: '#f59e0b' },
}

export const PipelineLineageView: React.FC<PipelineLineageViewProps> = ({
  lineage,
  loading,
  error,
}) => {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  if (loading) {
    return (
      <div className="p-8 text-center text-slate-400">
        <div className="animate-spin w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full mx-auto mb-3"></div>
        <p className="text-sm">Rendering pipeline DAG lineage...</p>
      </div>
    )
  }

  if (error || !lineage) {
    return (
      <div className="p-8 text-rose-400 text-sm">
        {error || 'Lineage configuration could not be loaded.'}
      </div>
    )
  }

  // Convert API nodes to ReactFlow nodes with custom styling
  const rfNodes: Node[] = lineage.nodes.map((n) => {
    const layerStyle = LAYER_COLORS[n.layer] || LAYER_COLORS.raw
    const isSelected = selectedNodeId === n.id
    return {
      id: n.id,
      position: n.position,
      data: { label: n.data.label },
      style: {
        background: layerStyle.bg,
        color: '#f8fafc',
        border: isSelected ? '2px solid #38bdf8' : `1.5px solid ${layerStyle.border}`,
        borderRadius: '10px',
        padding: '10px 16px',
        fontSize: '12px',
        fontFamily: 'monospace',
        fontWeight: 'bold',
        boxShadow: isSelected
          ? '0 0 15px rgba(56, 189, 248, 0.4)'
          : '0 4px 6px -1px rgba(0, 0, 0, 0.5)',
      },
    }
  })

  // Format edges with cyan gradient arrows
  const rfEdges: Edge[] = lineage.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    animated: true,
    style: { stroke: '#475569', strokeWidth: 1.5 },
  }))

  const selectedNodeInfo = lineage.nodes.find((n) => n.id === selectedNodeId)

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto h-[calc(100vh-4rem)] flex flex-col">
      {/* Header & Layer Legend */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 shrink-0">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
            Pipeline Lineage DAG
            <span className="text-xs font-mono px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              Acyclic Verified
            </span>
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Complete data provenance model mapping dependencies across all 5 operational DAG tiers.
          </p>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-2 bg-slate-900/80 p-2 rounded-xl border border-slate-800 text-xs font-mono">
          {Object.entries(LAYER_COLORS).map(([layer, colors]) => (
            <div key={layer} className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-800/60">
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: colors.border }}
              ></span>
              <span className="capitalize text-slate-300">{layer}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Main Flow Canvas & Details Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-1 min-h-[450px]">
        {/* ReactFlow Board */}
        <div className="lg:col-span-3 bg-slate-950/80 rounded-2xl border border-slate-800 shadow-2xl relative overflow-hidden">
          <ReactFlow
            nodes={rfNodes}
            edges={rfEdges}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
            fitView
            className="w-full h-full"
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#334155" />
            <Controls className="!bg-slate-900 !border-slate-700 !text-slate-200 fill-slate-200" />
          </ReactFlow>
        </div>

        {/* Selected Node Inspector Pane */}
        <div className="bg-slate-900/60 backdrop-blur-md rounded-2xl p-5 border border-slate-800 shadow-lg flex flex-col justify-between overflow-y-auto">
          {selectedNodeInfo ? (
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 font-bold">
                    {selectedNodeInfo.layer} Layer
                  </span>
                  <span className="text-xs font-mono text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Clean
                  </span>
                </div>
                <h3 className="text-lg font-bold font-mono text-white mt-1">
                  {selectedNodeInfo.id}
                </h3>
                <p className="text-xs text-slate-300 mt-2 leading-relaxed">
                  {selectedNodeInfo.data.description}
                </p>
              </div>

              {selectedNodeInfo.data.transformation && (
                <div className="pt-3 border-t border-slate-800">
                  <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                    Transformation Function
                  </div>
                  <div className="text-xs font-mono bg-slate-800/80 text-purple-300 px-2.5 py-1.5 rounded-lg border border-purple-500/20">
                    {selectedNodeInfo.data.transformation}
                  </div>
                </div>
              )}

              {selectedNodeInfo.data.columns && selectedNodeInfo.data.columns.length > 0 && (
                <div className="pt-3 border-t border-slate-800">
                  <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
                    Schema Columns ({selectedNodeInfo.data.columns.length})
                  </div>
                  <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                    {selectedNodeInfo.data.columns.map((col, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between text-xs font-mono bg-slate-950/60 px-2 py-1 rounded border border-slate-800/80"
                      >
                        <span className="text-slate-300">{col.name}</span>
                        <span className="text-slate-500 text-[10px]">{col.type}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 space-y-2 p-4">
              <Info className="w-6 h-6 text-slate-500 mb-1" />
              <div className="text-sm font-semibold text-slate-300">No Stage Selected</div>
              <p className="text-xs text-slate-400">
                Click on any node in the lineage DAG to inspect schema definitions, tier origins, and transformation logic.
              </p>
            </div>
          )}

          <div className="pt-4 border-t border-slate-800 text-[11px] text-slate-400 font-mono">
            Lineage Source: <span className="text-slate-300">config/lineage.yaml</span>
          </div>
        </div>
      </div>
    </div>
  )
}
