export default function Loading() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <div className="animate-pulse space-y-6">
        <div className="mx-auto h-10 w-48 rounded bg-gray-200" />
        <div className="mx-auto h-4 w-72 rounded bg-gray-200" />
        <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-28 rounded-xl bg-gray-200" />
          ))}
        </div>
        <div className="h-48 rounded-xl bg-gray-200" />
      </div>
    </div>
  )
}
