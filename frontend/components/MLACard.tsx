import Link from 'next/link'
import StatBadge from '@/components/StatBadge'
import type { MlaListItemEnriched } from '@/types'

interface Props {
  mla: MlaListItemEnriched
}

export default function MLACard({ mla }: Props) {
  return (
    <Link
      href={`/mlas/${mla.id}`}
      className="group flex flex-col gap-3 rounded-xl border border-gray-200 bg-white p-4
                 shadow-sm transition-all hover:border-navy/30 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold leading-tight text-gray-900 group-hover:text-navy">
          {mla.name}
        </h3>
        <StatBadge value={mla.party} variant="party" />
      </div>

      <div className="flex flex-col gap-0.5">
        <p className="text-xs font-medium text-gray-700">{mla.constituencyName}</p>
        <p className="text-xs text-gray-400">{mla.district}</p>
      </div>

      <div className="mt-auto pt-1 text-right">
        <span className="text-xs text-navy/40 transition-colors group-hover:text-navy">
          View profile →
        </span>
      </div>
    </Link>
  )
}
