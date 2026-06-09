export function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-4 p-4 md:p-8" aria-busy="true" aria-label="Loading">
      <div className="h-9 w-1/3 border-2 border-black bg-zinc-300" />
      <div className="h-4 w-2/3 border-2 border-black bg-zinc-200" />
      <div className="space-y-3 pt-4">
        <div className="h-20 border-2 border-black bg-zinc-200" />
        <div className="h-20 border-2 border-black bg-zinc-200" />
        <div className="h-20 border-2 border-black bg-zinc-200" />
      </div>
    </div>
  )
}
