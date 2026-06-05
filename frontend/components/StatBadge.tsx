type BadgeVariant = 'party' | 'district' | 'status' | 'reserved'

// All class strings must be complete literals so Tailwind JIT can detect them.
const PARTY_STYLES: Record<string, string> = {
  TVK:      'bg-orange-50 text-orange-700 border-orange-200',
  DMK:      'bg-red-50 text-red-700 border-red-200',
  AIADMK:   'bg-emerald-50 text-emerald-700 border-emerald-200',
  BJP:      'bg-amber-50 text-amber-700 border-amber-200',
  INC:      'bg-sky-50 text-sky-700 border-sky-200',
  PMK:      'bg-teal-50 text-teal-700 border-teal-200',
  VCK:      'bg-violet-50 text-violet-700 border-violet-200',
  DMDK:     'bg-yellow-50 text-yellow-700 border-yellow-200',
  IUML:     'bg-green-50 text-green-700 border-green-200',
  NTK:      'bg-rose-50 text-rose-700 border-rose-200',
  AMMK:     'bg-pink-50 text-pink-700 border-pink-200',
  'CPI(M)': 'bg-red-50 text-red-800 border-red-300',
  CPI:      'bg-red-50 text-red-700 border-red-200',
  IND:      'bg-gray-50 text-gray-600 border-gray-200',
}

const STATUS_STYLES: Record<string, string> = {
  filled:   'bg-green-50 text-green-700 border-green-200',
  vacant:   'bg-red-50 text-red-600 border-red-200',
  Minister: 'bg-accent/10 text-accent border-accent/20',
}

interface Props {
  value: string
  variant?: BadgeVariant
}

export default function StatBadge({ value, variant = 'party' }: Props) {
  let cls = 'bg-gray-50 text-gray-600 border-gray-200'

  if (variant === 'party') {
    cls = PARTY_STYLES[value] ?? 'bg-gray-50 text-gray-600 border-gray-200'
  } else if (variant === 'status') {
    cls = STATUS_STYLES[value] ?? 'bg-gray-50 text-gray-600 border-gray-200'
  } else if (variant === 'district') {
    cls = 'bg-slate-50 text-slate-600 border-slate-200'
  } else if (variant === 'reserved') {
    cls =
      value === 'GEN'
        ? 'bg-gray-50 text-gray-500 border-gray-200'
        : 'bg-blue-50 text-blue-700 border-blue-200'
  }

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${cls}`}
    >
      {value}
    </span>
  )
}
