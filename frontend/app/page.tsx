import Link from 'next/link'
import type { Metadata } from 'next'
import { getHealth, getMlas, getConstituencies } from '@/lib/api'
import StatBadge from '@/components/StatBadge'
import type { MlaListItem } from '@/types'

export const metadata: Metadata = {
  title: 'Tamil Nadu Assembly Dashboard',
}

function partyBreakdown(items: MlaListItem[]): [string, number][] {
  const counts: Record<string, number> = {}
  for (const m of items) counts[m.party] = (counts[m.party] ?? 0) + 1
  return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 5)
}

export default async function HomePage() {
  // All three fetches run in parallel; individual failures degrade gracefully.
  const [health, constituencies, mlas] = await Promise.allSettled([
    getHealth(),
    getConstituencies(),
    getMlas(),
  ])

  const healthData  = health.status       === 'fulfilled' ? health.value       : null
  const constData   = constituencies.status === 'fulfilled' ? constituencies.value : null
  const mlasData    = mlas.status         === 'fulfilled' ? mlas.value         : null

  const sittingMlas    = healthData?.mlas ?? 0
  const totalConst     = constData?.count ?? 0
  const vacantCount    = constData?.items.filter(c => c.status === 'vacant').length ?? 0
  const breakdown      = mlasData ? partyBreakdown(mlasData.items) : []
  const totalMlasForPct = mlasData?.count ?? 1

  return (
    <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">

      {/* Hero */}
      <div className="mb-12 text-center">
        <h1 className="text-5xl font-bold tracking-tight text-navy sm:text-6xl">
          TN<span className="text-accent">Watch</span>
        </h1>
        <p className="mt-3 text-lg text-gray-600">
          Independent civic accountability for Tamil Nadu
        </p>
        <p className="mt-1 text-sm text-gray-400">
          Facts with sources &mdash; no opinions, no accusations.
        </p>
      </div>

      {/* Assembly stats */}
      <div className="mb-10 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard value={sittingMlas} label="Sitting MLAs"
          sub="17th Tamil Nadu Legislative Assembly" />
        <StatCard value={totalConst} label="Constituencies"
          sub="Assembly constituencies across Tamil Nadu" />
        <StatCard value={vacantCount} label="Vacant Seats"
          sub="Pending by-elections as of latest data"
          alert={vacantCount > 0} />
      </div>

      {/* Party breakdown */}
      {breakdown.length > 0 && (
        <div className="mb-10 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-5 text-xs font-semibold uppercase tracking-widest text-gray-400">
            Top parties by seat count
          </h2>
          <div className="space-y-3">
            {breakdown.map(([party, count]) => (
              <div key={party} className="flex items-center gap-3">
                <div className="w-20 shrink-0">
                  <StatBadge value={party} variant="party" />
                </div>
                <div className="flex-1 overflow-hidden rounded-full bg-gray-100 h-2">
                  <div
                    className="h-full rounded-full bg-accent"
                    style={{ width: `${Math.max(3, (count / totalMlasForPct) * 100)}%` }}
                  />
                </div>
                <span className="w-8 shrink-0 text-right text-sm font-semibold text-gray-700">
                  {count}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* CTA */}
      <div className="text-center">
        <Link
          href="/mlas"
          className="inline-flex items-center gap-2 rounded-lg bg-navy px-6 py-3 text-sm
                     font-semibold text-white shadow-sm transition-colors hover:bg-navy-dark
                     focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2
                     focus-visible:outline-navy"
        >
          Browse all MLAs →
        </Link>
        <p className="mt-3 text-xs text-gray-400">
          Enrichment data (assets, criminal cases, performance scores) coming soon.
        </p>
      </div>

    </div>
  )
}

function StatCard({
  value,
  label,
  sub,
  alert = false,
}: {
  value: number
  label: string
  sub: string
  alert?: boolean
}) {
  return (
    <div
      className={`rounded-xl border p-6 shadow-sm ${
        alert ? 'border-red-200 bg-red-50' : 'border-gray-200 bg-white'
      }`}
    >
      <div className={`text-4xl font-bold tabular-nums ${alert ? 'text-red-600' : 'text-navy'}`}>
        {value}
      </div>
      <div className="mt-1 text-sm font-semibold text-gray-800">{label}</div>
      <div className="mt-0.5 text-xs text-gray-500">{sub}</div>
    </div>
  )
}
