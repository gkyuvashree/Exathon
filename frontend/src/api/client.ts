import type {
  OverviewData,
  MetricCatalogData,
  TimeseriesData,
  LineageData,
  IncidentsData,
} from '../types/api'

const API_BASE = '/api'

export async function fetchOverview(): Promise<OverviewData> {
  const res = await fetch(`${API_BASE}/overview`)
  if (!res.ok) throw new Error(`Overview fetch failed: ${res.statusText}`)
  return res.json()
}

export async function fetchMetricCatalog(): Promise<MetricCatalogData> {
  const res = await fetch(`${API_BASE}/metrics/catalog`)
  if (!res.ok) throw new Error(`Catalog fetch failed: ${res.statusText}`)
  return res.json()
}

export async function fetchTimeseries(
  metric: string,
  segment: string = 'ALL',
  startHour?: number,
  endHour?: number
): Promise<TimeseriesData> {
  const params = new URLSearchParams({ metric, segment })
  if (startHour !== undefined) params.append('start_hour', startHour.toString())
  if (endHour !== undefined) params.append('end_hour', endHour.toString())

  const res = await fetch(`${API_BASE}/metrics/timeseries?${params.toString()}`)
  if (!res.ok) throw new Error(`Timeseries fetch failed: ${res.statusText}`)
  return res.json()
}

export async function fetchLineage(): Promise<LineageData> {
  const res = await fetch(`${API_BASE}/lineage`)
  if (!res.ok) throw new Error(`Lineage fetch failed: ${res.statusText}`)
  return res.json()
}

export async function fetchIncidents(): Promise<IncidentsData> {
  const res = await fetch(`${API_BASE}/incidents`)
  if (!res.ok) throw new Error(`Incidents fetch failed: ${res.statusText}`)
  return res.json()
}
