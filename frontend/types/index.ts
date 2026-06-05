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

export interface ScoreBreakdownComponent {
  label: string;
  value: number;
  weight: number;
  source_url: string | null;
}

export interface ScoreBreakdown {
  components: ScoreBreakdownComponent[];
  total: number;
  version: string;
  calculated_at: string;
}

export interface MlaDetail {
  id: string;
  name: string;
  party: string;
  alliance: string | null;
  constituency: string;
  district: string;
  assemblyNumber: number | null;
  sourceUrl: string | null;
  lastUpdated: string | null;

  // enrichment fields — all nullable until scrapers run
  voteMargin: number | null;
  voteShare: number | null;
  totalAssets: string | null;
  totalLiabilities: string | null;
  criminalCases: number | null;
  criminalCasesSerious: number | null;
  performanceScore: number | null;
  scoreBreakdown: ScoreBreakdown | null;
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
