import type { Metadata } from 'next'
import { getMlas, getConstituencies } from '@/lib/api'
import MLAListClient from './MLAListClient'
import type { MlaListItemEnriched } from '@/types'

export const metadata: Metadata = { title: 'All MLAs' }

export default async function MLAListPage() {
  let mlaItems: MlaListItemEnriched[] = []
  let totalCount = 0
  let errorMsg: string | null = null

  try {
    const [mlaResp, constResp] = await Promise.all([getMlas(), getConstituencies()])
    totalCount = mlaResp.count

    const districtMap = new Map(constResp.items.map((c) => [c.id, c.district]))
    mlaItems = mlaResp.items.map((m) => ({
      ...m,
      district: districtMap.get(m.constituencyId) ?? 'Unknown',
    }))
  } catch {
    errorMsg = 'Could not load MLA data. Is the backend running on port 8000?'
  }

  if (errorMsg) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="rounded-xl border border-red-200 bg-red-50 p-8 text-center">
          <p className="text-sm font-medium text-red-600">{errorMsg}</p>
          <code className="mt-2 block text-xs text-red-400">
            uvicorn backend.app:app --port 8000
          </code>
        </div>
      </div>
    )
  }

  const districts = [...new Set(mlaItems.map((m) => m.district))].sort()
  const parties   = [...new Set(mlaItems.map((m) => m.party))].sort()

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-navy">Tamil Nadu MLAs</h1>
        <p className="mt-1 text-sm text-gray-500">
          17th Legislative Assembly &mdash; {totalCount} sitting members
        </p>
      </div>
      <MLAListClient
        mlas={mlaItems}
        districts={districts}
        parties={parties}
        totalCount={totalCount}
      />
    </div>
  )
}
