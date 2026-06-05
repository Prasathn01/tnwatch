import Link from 'next/link'
import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import { getMla, getConstituencies } from '@/lib/api'
import StatBadge from '@/components/StatBadge'
import type { MlaDetail } from '@/types'

interface Props {
  params: Promise<{ id: string }>
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params
  try {
    const mla = await getMla(id)
    return { title: `${mla.name} — ${mla.constituencyName}` }
  } catch {
    return { title: 'MLA Not Found' }
  }
}

function formatDate(iso: string | null | undefined): string | null {
  if (!iso) return null
  return new Date(iso).toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
  })
}

function formatAssets(raw: string | null): string | null {
  if (!raw) return null
  // Strip currency symbols, commas, spaces; keep digits and decimal
  const num = parseFloat(raw.replace(/[^0-9.]/g, ''))
  if (isNaN(num) || num <= 0) return raw
  if (num >= 1_00_00_000) return `₹${(num / 1_00_00_000).toFixed(2)} Cr`
  if (num >= 1_00_000) return `₹${(num / 1_00_000).toFixed(2)} L`
  return `₹${Math.round(num).toLocaleString('en-IN')}`
}

function formatVoteMargin(margin: number): string {
  const abs = Math.abs(margin).toLocaleString('en-IN')
  return margin >= 0 ? `+${abs} votes` : `−${abs} votes`
}

export default async function MLADetailPage({ params }: Props) {
  const { id } = await params
  let mla: MlaDetail | undefined
  let district = 'Unknown'

  try {
    const [mlaData, constData] = await Promise.all([
      getMla(id),
      getConstituencies(),
    ])
    mla = mlaData
    district = constData.items.find((c) => c.id === mlaData.constituencyId)?.district ?? 'Unknown'
  } catch (err: unknown) {
    if (err instanceof Error && err.message.includes('404')) notFound()
    throw err
  }

  if (!mla) notFound()

  const pageUpdated = formatDate(mla.lastUpdated)
  const scoreUpdated = formatDate(mla.scoreBreakdown?.calculated_at ?? mla.lastUpdated)

  const criminalCount = mla.criminalCases ?? 0
  const criminalBadgeClass =
    criminalCount === 0 ? 'bg-green-100 text-green-800' :
    criminalCount <= 2  ? 'bg-amber-100 text-amber-800' :
                          'bg-red-100 text-red-800'

  const score = mla.performanceScore
  const scoreBarClass =
    score === null ? '' :
    score <= 40    ? 'bg-red-500' :
    score <= 70    ? 'bg-amber-500' :
                     'bg-green-500'

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">

      <Link
        href="/mlas"
        className="mb-6 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-navy"
      >
        ← Back to all MLAs
      </Link>

      {/* Header card */}
      <div className="mb-8 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-bold text-navy sm:text-3xl">{mla.name}</h1>
            <p className="mt-1 text-base text-gray-600">
              {mla.constituencyName} &middot; {district}
            </p>
            {mla.isMinister && mla.portfolio && (
              <p className="mt-1 text-sm font-semibold text-accent">{mla.portfolio}</p>
            )}
          </div>
          <div className="flex flex-wrap gap-2 pt-1">
            <StatBadge value={mla.party} variant="party" />
            {mla.isMinister && <StatBadge value="Minister" variant="status" />}
          </div>
        </div>
      </div>

      {/* Two-column detail */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">

        {/* Left: profile */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-gray-400">
            Profile
          </h2>
          <dl className="space-y-3">
            <ProfileRow label="Party"        value={mla.party} />
            {mla.alliance && <ProfileRow label="Alliance"     value={mla.alliance} />}
            <ProfileRow label="Constituency" value={mla.constituencyName} />
            <ProfileRow label="District"     value={district} />
            <ProfileRow label="Assembly"     value={`${mla.assemblyNumber}th Assembly`} />
            {mla.electedYear && <ProfileRow label="Elected"   value={String(mla.electedYear)} />}
            {mla.age         && <ProfileRow label="Age"       value={String(mla.age)} />}
            {mla.education   && <ProfileRow label="Education" value={mla.education} />}
            {mla.profession  && <ProfileRow label="Profession" value={mla.profession} />}
          </dl>
        </div>

        {/* Right: enrichment */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-gray-400">
            Performance &amp; Assets
          </h2>
          <dl className="space-y-4">

            <EnrichmentRow label="Vote Margin" updatedAt={mla.voteMargin !== null ? pageUpdated : null}>
              {mla.voteMargin !== null
                ? <span className="text-sm text-gray-800">{formatVoteMargin(mla.voteMargin)}</span>
                : <Pending />}
            </EnrichmentRow>

            <EnrichmentRow label="Vote Share" updatedAt={mla.voteShare !== null ? pageUpdated : null}>
              {mla.voteShare !== null
                ? <span className="text-sm text-gray-800">{mla.voteShare}%</span>
                : <Pending />}
            </EnrichmentRow>

            <EnrichmentRow label="Declared Assets" updatedAt={mla.totalAssets !== null ? pageUpdated : null}>
              {mla.totalAssets !== null
                ? <span className="text-sm text-gray-800">{formatAssets(mla.totalAssets)}</span>
                : <Pending />}
            </EnrichmentRow>

            <EnrichmentRow label="Liabilities" updatedAt={mla.totalLiabilities !== null ? pageUpdated : null}>
              {mla.totalLiabilities !== null
                ? <span className="text-sm text-gray-800">{formatAssets(mla.totalLiabilities)}</span>
                : <Pending />}
            </EnrichmentRow>

            <EnrichmentRow label="Criminal Cases" updatedAt={mla.criminalCases !== null ? pageUpdated : null}>
              {mla.criminalCases !== null
                ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${criminalBadgeClass}`}>
                      {criminalCount} case{criminalCount !== 1 ? 's' : ''}
                    </span>
                    {mla.criminalCasesSerious !== null && mla.criminalCasesSerious > 0 && (
                      <span className="text-xs text-red-600">
                        ({mla.criminalCasesSerious} serious)
                      </span>
                    )}
                  </div>
                )
                : <Pending />}
            </EnrichmentRow>

            <EnrichmentRow label="Performance Score" updatedAt={score !== null ? scoreUpdated : null}>
              {score !== null
                ? (
                  <div className="w-full">
                    <div className="mb-1.5 flex items-baseline justify-between">
                      <span className="text-sm font-semibold text-gray-800">{score}/100</span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                      <div
                        className={`h-2 rounded-full transition-all ${scoreBarClass}`}
                        style={{ width: `${score}%` }}
                      />
                    </div>
                  </div>
                )
                : <Pending />}
            </EnrichmentRow>
          </dl>

          {/* Score breakdown collapsible */}
          {mla.scoreBreakdown && (
            <details className="mt-6 rounded-lg border border-gray-100 bg-gray-50">
              <summary className="cursor-pointer select-none px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 hover:text-navy">
                Score breakdown ▸
              </summary>
              <div className="divide-y divide-gray-100 px-4 pb-3 pt-1">
                {mla.scoreBreakdown.components.map((c, i) => (
                  <div key={i} className="flex items-center justify-between gap-3 py-2">
                    <span className="text-xs text-gray-600">
                      {c.source_url
                        ? (
                          <a
                            href={c.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="underline underline-offset-2 hover:text-navy"
                          >
                            {c.label}
                          </a>
                        )
                        : c.label}
                    </span>
                    <span className={`shrink-0 text-xs font-semibold tabular-nums ${c.delta >= 0 ? 'text-green-700' : 'text-red-600'}`}>
                      {c.delta >= 0 ? '+' : ''}{c.delta}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      </div>

      {/* Source note */}
      <div className="mt-6 flex flex-col gap-1 rounded-lg bg-gray-50 px-4 py-3 text-xs
                      text-gray-500 sm:flex-row sm:items-center sm:justify-between">
        <span>
          Data sourced from public records.{' '}
          {mla.sourceUrl && (
            <a
              href={mla.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2 hover:text-navy"
            >
              View source
            </a>
          )}
        </span>
        {pageUpdated && (
          <span className="text-gray-400">Page last updated: {pageUpdated}</span>
        )}
      </div>

    </div>
  )
}

function ProfileRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-gray-50 pb-2 last:border-0 last:pb-0">
      <dt className="shrink-0 text-xs font-medium text-gray-500">{label}</dt>
      <dd className="text-right text-sm text-gray-800">{value}</dd>
    </div>
  )
}

function EnrichmentRow({
  label,
  updatedAt,
  children,
}: {
  label: string
  updatedAt: string | null
  children: React.ReactNode
}) {
  return (
    <div className="border-b border-gray-50 pb-3 last:border-0 last:pb-0">
      <dt className="mb-1 text-xs font-medium text-gray-500">{label}</dt>
      <dd className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">{children}</div>
        {updatedAt && (
          <span className="shrink-0 whitespace-nowrap text-[10px] leading-5 text-gray-300">
            Updated: {updatedAt}
          </span>
        )}
      </dd>
    </div>
  )
}

function Pending() {
  return <span className="text-xs italic text-gray-400">Data pending</span>
}
