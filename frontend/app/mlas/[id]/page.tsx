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

  const lastUpdated = mla.lastUpdated
    ? new Date(mla.lastUpdated).toLocaleDateString('en-IN', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      })
    : null

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">

      {/* Back link */}
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
            {mla.alliance && <ProfileRow label="Alliance" value={mla.alliance} />}
            <ProfileRow label="Constituency" value={mla.constituencyName} />
            <ProfileRow label="District"     value={district} />
            <ProfileRow label="Assembly"     value={`${mla.assemblyNumber}th Assembly`} />
            {mla.electedYear  && <ProfileRow label="Elected"    value={String(mla.electedYear)} />}
            {mla.age          && <ProfileRow label="Age"         value={String(mla.age)} />}
            {mla.education    && <ProfileRow label="Education"   value={mla.education} />}
            {mla.profession   && <ProfileRow label="Profession"  value={mla.profession} />}
          </dl>
        </div>

        {/* Right: enrichment (grayed placeholders where null) */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-gray-400">
            Performance &amp; Assets
          </h2>
          <dl className="space-y-3">
            <EnrichmentRow
              label="Vote Margin"
              value={mla.voteMargin !== null
                ? `${mla.voteMargin.toLocaleString('en-IN')} votes`
                : null}
            />
            <EnrichmentRow
              label="Vote Share"
              value={mla.voteSharePct !== null ? `${mla.voteSharePct}%` : null}
            />
            <EnrichmentRow
              label="Declared Assets"
              value={mla.declaredAssetsCr !== null ? `₹${mla.declaredAssetsCr} Cr` : null}
            />
            <EnrichmentRow
              label="Liabilities"
              value={mla.liabilitiesCr !== null ? `₹${mla.liabilitiesCr} Cr` : null}
            />
            <EnrichmentRow
              label="Criminal Cases"
              value={mla.criminalCases > 0 ? String(mla.criminalCases) : null}
            />
            <EnrichmentRow
              label="Performance Score"
              value={mla.performanceScore !== null ? `${mla.performanceScore}/100` : null}
            />
          </dl>

          <div className="mt-6 rounded-lg border border-amber-100 bg-amber-50 px-4 py-3">
            <p className="text-xs text-amber-600">
              ECI affidavit data and performance scores are being collected. Check back soon.
            </p>
          </div>
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
        {lastUpdated && (
          <span className="text-gray-400">Last updated: {lastUpdated}</span>
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

function EnrichmentRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-gray-50 pb-2 last:border-0 last:pb-0">
      <dt className="shrink-0 text-xs font-medium text-gray-500">{label}</dt>
      <dd className={`text-right text-sm ${value !== null ? 'text-gray-800' : 'italic text-gray-300'}`}>
        {value ?? 'Coming soon'}
      </dd>
    </div>
  )
}
