export default function MLAListLoading() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-6 animate-pulse space-y-2">
        <div className="h-8 w-52 rounded bg-gray-200" />
        <div className="h-4 w-72 rounded bg-gray-200" />
      </div>
      <div className="mb-6 flex animate-pulse flex-col gap-3 sm:flex-row">
        <div className="h-10 flex-1 rounded-lg bg-gray-200" />
        <div className="h-10 w-40 rounded-lg bg-gray-200" />
        <div className="h-10 w-36 rounded-lg bg-gray-200" />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: 16 }).map((_, i) => (
          <div key={i} className="h-32 animate-pulse rounded-xl bg-gray-200" />
        ))}
      </div>
    </div>
  )
}
