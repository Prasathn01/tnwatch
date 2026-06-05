import Link from 'next/link'
import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import { getMla } from '@/lib/api'
import type { MlaDetail, ScoreBreakdown } from '@/types'

interface Props {
  params: Promise<{ id: string }>
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params
  try {
    const mla = await getMla(id)
    return { title: `${mla.name} — ${mla.constituency}` }
  } catch {
    return { title: 'MLA Not Found' }
  }
}

const Pending = () => (
  <span className="text-xs text-gray-400">Data pending</span>
)

function formatAssets(raw: string | null): string | null {
  if (!raw) return null
  const num = parseFloat(raw.replace(/[^0-9.]/g, ''))
  if (isNaN(num)) return raw
  if (num >= 10000000) return `₹${(num / 10000000).toFixed(2)} Cr`
  if (num >= 100000)   return `₹${(num / 100000).toFixed(2)} L`
  return `₹${num.toLocaleString('en-IN')}`
}

function formatVoteMargin(n: number | null): string | null {
  if (n == null) return null
  return `+${n.toLocaleString('en-IN')} votes`
}

function formatVoteShare(n: number | null): string | null {
  if (n == null) return null
  return `${n.toFixed(1)}%`
}

function CriminalBadge({ total, serious }: {
  total: number | null,
  serious: number | null
}) {
  if (total == null) return <Pending />
  const colour = total === 0
    ? 'bg-green-100 text-green-800'
    : total <= 2
      ? 'bg-amber-100 text-amber-800'
      : 'bg-red-100 text-red-800'
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colour}`}>
      {total} case{total !== 1 ? 's' : ''}
      {serious != null && serious > 0 && ` (${serious} serious)`}
    </span>
  )
}

function ScoreBar({ score }: { score: number | null }) {
  if (score == null) return <Pending />
  const colour = score < 40
    ? 'bg-red-500'
    : score < 70
      ? 'bg-amber-500'
      : 'bg-green-500'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-200 rounded h-2">
        <div
          className={`h-2 rounded ${colour}`}
          style={{ width: `${score}%` }}
        />
      </div>
      <span className="text-sm font-medium">{score}/100</span>
    </div>
  )
}

function BreakdownSection({ breakdown }: {
  breakdown: ScoreBreakdown | null
}) {
  if (!breakdown) return null
  return (
    <details className="mt-2 text-sm">
      <summary className="cursor-pointer text-gray-500 hover:text-gray-700">
        Score breakdown
      </summary>
      <ul className="mt-2 space-y-1 pl-2">
        {breakdown.components.map((c, i) => (
          <li key={i} className="flex justify-between text-xs text-gray-600">
            <span>
              {c.source_url
                ? <a href={c.source_url} className="underline">{c.label}</a>
                : c.label
              }
            </span>
            <span>{c.value} × {c.weight}</span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-gray-400 mt-1">
        Calculated: {new Date(breakdown.calculated_at).toLocaleDateString()}
      </p>
    </details>
  )
}

export default async function MLADetailPage({ params }: Props) {
  const { id } = await params
  let mla: MlaDetail

  try {
    mla = await getMla(id)
  } catch (err: unknown) {
    if (err instanceof Error && err.message.includes('404')) notFound()
    throw err
  }

  const scoreTimestamp: string | null =
    mla.scoreBreakdown?.calculated_at ?? mla.lastUpdated ?? null

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
        <h1 className="text-2xl font-bold text-navy sm:text-3xl">{mla.name}</h1>
        <p className="mt-1 text-base text-gray-600">
          {mla.constituency} &middot; {mla.district}
        </p>
        <p className="mt-1 text-sm text-gray-500">{mla.party}</p>
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
            {mla.alliance != null && <ProfileRow label="Alliance" value={mla.alliance} />}
            <ProfileRow label="Constituency" value={mla.constituency} />
            <ProfileRow label="District"     value={mla.district} />
            {mla.assemblyNumber != null && (
              <ProfileRow label="Assembly" value={`${mla.assemblyNumber}th Assembly`} />
            )}
          </dl>
        </div>

        {/* Right: Performance & Assets */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-gray-400">
            Performance &amp; Assets
          </h2>
          <dl className="space-y-4">

            <EnrichmentRow
              label="Vote Margin"
              timestamp={mla.voteMargin != null ? mla.lastUpdated : null}
            >
              {formatVoteMargin(mla.voteMargin) ?? <Pending />}
            </EnrichmentRow>

            <EnrichmentRow
              label="Vote Share"
              timestamp={mla.voteShare != null ? mla.lastUpdated : null}
            >
              {formatVoteShare(mla.voteShare) ?? <Pending />}
            </EnrichmentRow>

            <EnrichmentRow
              label="Declared Assets"
              timestamp={mla.totalAssets != null ? mla.lastUpdated : null}
            >
              {formatAssets(mla.totalAssets) ?? <Pending />}
            </EnrichmentRow>

            <EnrichmentRow
              label="Liabilities"
              timestamp={mla.totalLiabilities != null ? mla.lastUpdated : null}
            >
              {formatAssets(mla.totalLiabilities) ?? <Pending />}
            </EnrichmentRow>

            <EnrichmentRow
              label="Criminal Cases"
              timestamp={mla.criminalCases != null ? mla.lastUpdated : null}
            >
              <CriminalBadge total={mla.criminalCases} serious={mla.criminalCasesSerious} />
            </EnrichmentRow>

            <EnrichmentRow
              label="Performance Score"
              timestamp={mla.performanceScore != null ? scoreTimestamp : null}
            >
              <>
                <ScoreBar score={mla.performanceScore} />
                <BreakdownSection breakdown={mla.scoreBreakdown} />
              </>
            </EnrichmentRow>

          </dl>
        </div>
      </div>

      {/* Source footer */}
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
        {mla.lastUpdated && (
          <span className="text-gray-400">
            Last updated: {new Date(mla.lastUpdated).toLocaleDateString('en-IN')}
          </span>
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
  timestamp,
  children,
}: {
  label: string
  timestamp: string | null | undefined
  children: React.ReactNode
}) {
  return (
    <div className="border-b border-gray-50 pb-3 last:border-0 last:pb-0">
      <dt className="mb-1 text-xs font-medium text-gray-500">{label}</dt>
      <dd className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">{children}</div>
        {timestamp && (
          <span className="shrink-0 whitespace-nowrap text-xs text-gray-400">
            Updated: {new Date(timestamp).toLocaleDateString('en-IN')}
          </span>
        )}
      </dd>
    </div>
  )
}
