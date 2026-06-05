export default function MLADetailLoading() {
  return (
    <div className="mx-auto max-w-5xl animate-pulse px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-6 h-4 w-28 rounded bg-gray-200" />
      <div className="mb-8 h-32 rounded-xl bg-gray-200" />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="h-64 rounded-xl bg-gray-200" />
        <div className="h-64 rounded-xl bg-gray-200" />
      </div>
      <div className="mt-6 h-10 rounded-lg bg-gray-200" />
    </div>
  )
}
