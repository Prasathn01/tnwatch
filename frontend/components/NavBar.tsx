import Link from 'next/link'

export default function NavBar() {
  return (
    <nav className="bg-navy text-white shadow-md">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <Link href="/" className="flex items-center gap-1 select-none">
            <span className="text-xl font-bold tracking-tight">
              TN<span className="text-accent">Watch</span>
            </span>
          </Link>

          <div className="flex items-center gap-6">
            <Link
              href="/"
              className="text-sm font-medium text-white/75 transition-colors hover:text-white"
            >
              Home
            </Link>
            <Link
              href="/mlas"
              className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-white
                         transition-colors hover:bg-accent-dark focus-visible:outline
                         focus-visible:outline-2 focus-visible:outline-offset-2
                         focus-visible:outline-accent"
            >
              Browse MLAs
            </Link>
          </div>
        </div>
      </div>
    </nav>
  )
}
