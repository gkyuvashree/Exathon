export interface TrendPoint {
  hour_ts: number
  timestamp: string
  revenue: number
  orders: number
}

export interface OverviewData {
  pipeline_status: string
  total_monitored_metrics: number
  latest_hour: number
  latest_timestamp: string
  last_24h_revenue: number
  last_24h_orders: number
  active_incidents_count: number
  hourly_trends_24h: TrendPoint[]
}

export interface MetricCatalogItem {
  node: string
  name: string
  kind: string
  description?: string
}

export interface CategoryGroup {
  group: string
  metric_count: number
  metrics: MetricCatalogItem[]
}

export interface MetricCatalogData {
  total_metrics: number
  groups: CategoryGroup[]
}

export interface MetricDataPoint {
  hour_ts: number
  timestamp: string
  value: number
}

export interface TimeseriesData {
  metric: string
  segment: string
  node: string
  start_hour: number
  end_hour: number
  count: number
  data: MetricDataPoint[]
}

export interface LineageNodeData {
  label: string
  layer: string
  description: string
  columns?: Array<{ name: string; type: string }>
  transformation?: string
}

export interface LineageNode {
  id: string
  layer: string
  data: LineageNodeData
  position: { x: number; y: number }
}

export interface LineageEdge {
  id: string
  source: string
  target: string
  animated?: boolean
}

export interface LineageData {
  nodes: LineageNode[]
  edges: LineageEdge[]
}

export interface IncidentContributor {
  metric: string
  contribution_pct: number
}

export interface IncidentRecord {
  id: string
  incident_type: string
  verdict: string
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | string
  status: string
  onset_hour: number
  onset_timestamp: string
  duration_hours: number
  target_stage: string
  affected_metrics: string[]
  description: string
  diagnostic_details: Record<string, any>
  top_contributors: IncidentContributor[]
  is_demo: boolean
}

export interface IncidentsData {
  total_incidents: number
  incidents: IncidentRecord[]
}
