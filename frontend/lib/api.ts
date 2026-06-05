// Typed fetch wrappers for the TNWatch FastAPI backend.
// Server components use BACKEND_URL directly (absolute URL required for ISR).
// The next.config.js rewrite (/api/* → localhost:8000/*) handles any future
// client-side fetches without CORS issues.

import type {
  HealthResponse,
  MlaListItem,
  MlaListResponse,
  MlaDetail,
  ScoreBreakdown,
  ConstituencyItem,
  ConstituencyListResponse,
} from '@/types'

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000'

async function backendFetch<T>(path: string, revalidate = 3600): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    next: { revalidate },
  })
  if (!res.ok) {
    throw new Error(`Backend ${res.status} for ${path}`)
  }
  return res.json() as Promise<T>
}

// --- raw snake_case shapes from the FastAPI wire format ---

interface RawMlaListItem {
  id: string
  name: string
  party: string
  constituency_id: string
  constituency_name: string
}

interface RawMlaDetail {
  id: string
  name: string
  party: string
  alliance: string | null
  constituency_name: string
  district: string
  assembly_number: number | null
  source_url: string | null
  last_updated: string | null
  vote_margin: number | null
  vote_share: number | null
  total_assets: string | null
  total_liabilities: string | null
  criminal_cases: number | null
  criminal_cases_serious: number | null
  performance_score: number | null
  score_breakdown: object | null
}

interface RawConstituencyItem {
  id: string
  number: number
  name: string
  district: string
  lok_sabha_seat: string | null
  total_electors: number | null
  reserved: string
  status: 'filled' | 'vacant'
}

// --- mapping helpers ---

function mapMla(raw: RawMlaListItem): MlaListItem {
  return {
    id: raw.id,
    name: raw.name,
    party: raw.party,
    constituencyId: raw.constituency_id,
    constituencyName: raw.constituency_name,
  }
}

function mapMlaDetail(raw: RawMlaDetail): MlaDetail {
  return {
    id: raw.id,
    name: raw.name,
    party: raw.party,
    alliance: raw.alliance ?? null,
    constituency: raw.constituency_name,
    district: raw.district,
    assemblyNumber: raw.assembly_number ?? null,
    sourceUrl: raw.source_url ?? null,
    lastUpdated: raw.last_updated ?? null,
    voteMargin: raw.vote_margin ?? null,
    voteShare: raw.vote_share ?? null,
    totalAssets: raw.total_assets ?? null,
    totalLiabilities: raw.total_liabilities ?? null,
    criminalCases: raw.criminal_cases ?? null,
    criminalCasesSerious: raw.criminal_cases_serious ?? null,
    performanceScore: raw.performance_score ?? null,
    scoreBreakdown: (raw.score_breakdown as ScoreBreakdown) ?? null,
  }
}

function mapConstituency(raw: RawConstituencyItem): ConstituencyItem {
  return {
    id: raw.id,
    number: raw.number,
    name: raw.name,
    district: raw.district,
    lokSabhaSeat: raw.lok_sabha_seat,
    totalElectors: raw.total_electors,
    reserved: raw.reserved,
    status: raw.status,
  }
}

// --- public API functions ---

export async function getHealth(): Promise<HealthResponse> {
  return backendFetch<HealthResponse>('/health')
}

export async function getMlas(params?: {
  district?: string
  party?: string
}): Promise<MlaListResponse> {
  const qs = new URLSearchParams()
  if (params?.district) qs.set('district', params.district)
  if (params?.party) qs.set('party', params.party)
  const query = qs.toString() ? `?${qs}` : ''
  const raw = await backendFetch<{ count: number; items: RawMlaListItem[] }>(`/mlas${query}`)
  return { count: raw.count, items: raw.items.map(mapMla) }
}

export async function getMla(id: string): Promise<MlaDetail> {
  const raw = await backendFetch<RawMlaDetail>(`/mlas/${id}`)
  return mapMlaDetail(raw)
}

export async function getConstituencies(): Promise<ConstituencyListResponse> {
  const raw = await backendFetch<{ count: number; items: RawConstituencyItem[] }>('/constituencies')
  return { count: raw.count, items: raw.items.map(mapConstituency) }
}
