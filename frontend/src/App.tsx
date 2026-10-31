import { useState, useEffect } from 'react'
import { Sidebar, type TabId } from './components/Sidebar'
import { OverviewView } from './components/OverviewView'
import { AnomaliesView } from './components/AnomaliesView'
import { IncidentDetailModal } from './components/IncidentDetailModal'
import { MetricExplorerView } from './components/MetricExplorerView'
import { PipelineLineageView } from './components/PipelineLineageView'
import {
  fetchOverview,
  fetchMetricCatalog,
  fetchLineage,
  fetchIncidents,
} from './api/client'
import type {
  OverviewData,
  MetricCatalogData,
  LineageData,
  IncidentRecord,
} from './types/api'

export function App() {
  const [activeTab, setActiveTab] = useState<TabId>('overview')
  const [selectedIncident, setSelectedIncident] = useState<IncidentRecord | null>(null)

  // State
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [loadingOverview, setLoadingOverview] = useState<boolean>(true)
  const [errorOverview, setErrorOverview] = useState<string | null>(null)

  const [catalog, setCatalog] = useState<MetricCatalogData | null>(null)
  const [loadingCatalog, setLoadingCatalog] = useState<boolean>(true)

  const [lineage, setLineage] = useState<LineageData | null>(null)
  const [loadingLineage, setLoadingLineage] = useState<boolean>(true)

  const [incidents, setIncidents] = useState<IncidentRecord[]>([])
  const [loadingIncidents, setLoadingIncidents] = useState<boolean>(true)
  const [errorIncidents, setErrorIncidents] = useState<string | null>(null)

  // Initial Load
  const loadInitialData = async () => {
    setLoadingOverview(true)
    setErrorOverview(null)
    try {
      const o = await fetchOverview()
      setOverview(o)
    } catch (err: any) {
      setErrorOverview(err.message || 'Failed to load system overview')
    } finally {
      setLoadingOverview(false)
    }

    try {
      const c = await fetchMetricCatalog()
      setCatalog(c)
    } catch (err) {
      console.error(err)
    } finally {
      setLoadingCatalog(false)
    }

    try {
      const l = await fetchLineage()
      setLineage(l)
    } catch (err) {
      console.error(err)
    } finally {
      setLoadingLineage(false)
    }

    try {
      const inc = await fetchIncidents()
      setIncidents(inc.incidents)
    } catch (err: any) {
      setErrorIncidents(err.message || 'Failed to load incidents')
    } finally {
      setLoadingIncidents(false)
    }
  }

  useEffect(() => {
    loadInitialData()
  }, [])

  return (
    <div className="flex h-screen bg-[#060913] text-slate-100 font-sans overflow-hidden">
      {/* Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        pipelineStatus={overview?.pipeline_status || 'ONLINE'}
        totalMetrics={catalog?.total_metrics || 46}
        activeIncidents={incidents.length}
      />

      {/* Main Viewport */}
      <main className="flex-1 flex flex-col h-screen overflow-y-auto bg-gradient-to-b from-[#0b1120] to-[#060913]">
        {activeTab === 'overview' && (
          <OverviewView
            data={overview}
            loading={loadingOverview}
            error={errorOverview}
            onRefresh={loadInitialData}
            onNavigateToIncidents={() => setActiveTab('anomalies')}
          />
        )}

        {activeTab === 'anomalies' && (
          <AnomaliesView
            incidents={incidents}
            loading={loadingIncidents}
            error={errorIncidents}
            onSelectIncident={setSelectedIncident}
          />
        )}

        {activeTab === 'explorer' && (
          <MetricExplorerView
            catalog={catalog}
            loadingCatalog={loadingCatalog}
          />
        )}

        {activeTab === 'lineage' && (
          <PipelineLineageView
            lineage={lineage}
            loading={loadingLineage}
            error={null}
          />
        )}
      </main>

      {/* Deep-Dive Incident Card Modal */}
      <IncidentDetailModal
        incident={selectedIncident}
        onClose={() => setSelectedIncident(null)}
      />
    </div>
  )
}

export default App
