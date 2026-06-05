// Typed fetch wrappers for the TNWatch FastAPI backend.
// Server components use BACKEND_URL directly (absolute URL required for ISR).
// The next.config.js rewrite (/api/* → localhost:8000/*) handles any future
// client-side fetches without CORS issues.

import type {
  HealthResponse,
  MlaListItem,
  MlaListResponse,
  MlaDetail,
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
  constituency_id: string
  constituency_name: string
  name: string
  party: string
  alliance: string | null
  assembly_number: number
  elected_year: number | null
  vote_margin: number | null
  vote_share_pct: string | null
  age: number | null
  education: string | null
  profession: string | null
  declared_assets_cr: string | null
  liabilities_cr: string | null
  criminal_cases: number
  is_minister: boolean
  portfolio: string | null
  photo_url: string | null
  performance_score: string | null
  source_url: string | null
  last_updated: string | null
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
    constituencyId: raw.constituency_id,
    constituencyName: raw.constituency_name,
    name: raw.name,
    party: raw.party,
    alliance: raw.alliance,
    assemblyNumber: raw.assembly_number,
    electedYear: raw.elected_year,
    voteMargin: raw.vote_margin,
    voteSharePct: raw.vote_share_pct,
    age: raw.age,
    education: raw.education,
    profession: raw.profession,
    declaredAssetsCr: raw.declared_assets_cr,
    liabilitiesCr: raw.liabilities_cr,
    criminalCases: raw.criminal_cases,
    isMinister: raw.is_minister,
    portfolio: raw.portfolio,
    photoUrl: raw.photo_url,
    performanceScore: raw.performance_score,
    sourceUrl: raw.source_url,
    lastUpdated: raw.last_updated,
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
