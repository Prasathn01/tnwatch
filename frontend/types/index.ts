// TypeScript interfaces for TNWatch API responses.
// Field names follow camelCase (CONTEXT.md §9 Rule 3); mapping from the
// snake_case wire format happens in lib/api.ts.

export interface HealthResponse {
  status: string
  mlas: number
}

export interface MlaListItem {
  id: string
  name: string
  party: string
  constituencyId: string
  constituencyName: string
}

// MlaListItem enriched with district (joined server-side from constituencies)
export interface MlaListItemEnriched extends MlaListItem {
  district: string
}

export interface MlaListResponse {
  count: number
  items: MlaListItem[]
}

export interface MlaDetail {
  id: string
  constituencyId: string
  constituencyName: string
  name: string
  party: string
  alliance: string | null
  assemblyNumber: number
  electedYear: number | null
  voteMargin: number | null
  voteSharePct: string | null
  age: number | null
  education: string | null
  profession: string | null
  declaredAssetsCr: string | null
  liabilitiesCr: string | null
  criminalCases: number
  isMinister: boolean
  portfolio: string | null
  photoUrl: string | null
  performanceScore: string | null
  sourceUrl: string | null
  lastUpdated: string | null
}

export interface ConstituencyItem {
  id: string
  number: number
  name: string
  district: string
  lokSabhaSeat: string | null
  totalElectors: number | null
  reserved: string
  status: 'filled' | 'vacant'
}

export interface ConstituencyListResponse {
  count: number
  items: ConstituencyItem[]
}
