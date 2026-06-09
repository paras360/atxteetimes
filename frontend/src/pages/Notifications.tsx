import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { api, FoundSlot } from '../api/client'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { timeAgo } from '../lib/time'

function isStale(iso: string): boolean {
  return Date.now() - new Date(iso).getTime() > 60 * 60 * 1000 // > 1 hour
}

export default function Notifications() {
  const [slots, setSlots] = useState<FoundSlot[] | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .getFoundSlots(100)
      .then((res) => setSlots(res.data))
      .catch(() => {
        setError(true)
        toast.error('Failed to load opportunities')
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingSkeleton />

  return (
    <div className="p-4 md:p-8 space-y-6">
      <div>
        <h2 className="text-3xl md:text-4xl font-black">Opportunities</h2>
        <p className="text-zinc-700 mt-1 text-sm">
          Tee times we found matching your watches. Book quickly - cancellations get grabbed fast.
        </p>
      </div>

      {error ? (
        <div className="page-card p-6 text-sm text-red-700">
          Couldn't load opportunities. Please try again.
        </div>
      ) : (slots?.length ?? 0) === 0 ? (
        <div className="page-card p-6 text-zinc-600 text-sm">
          Nothing found yet. We'll email you the moment a matching slot opens up.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {slots!.map((s) => {
            const stale = isStale(s.found_at)
            return (
              <div key={s.id} className="page-card list-item p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-bold text-lg">{s.course_name}</div>
                    <div className="text-sm text-zinc-700 mt-0.5">
                      {s.date} · {s.time}
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span className="text-[10px] uppercase tracking-[0.14em] border-2 border-black px-2 py-0.5 bg-black text-white">
                        {s.open_slots} open
                      </span>
                      <span className={`text-[10px] uppercase tracking-[0.14em] border-2 border-black px-2 py-0.5 ${stale ? 'bg-zinc-200 text-zinc-600' : 'bg-white'}`}>
                        {stale ? 'May be gone' : 'Fresh'}
                      </span>
                      <span className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">
                        found {timeAgo(s.found_at)}
                      </span>
                    </div>
                  </div>
                  <a className="button shrink-0" href={s.booking_url} target="_blank" rel="noopener noreferrer">
                    Open WebTrac
                  </a>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {(slots?.length ?? 0) > 0 && (
        <div className="page-card p-4 text-xs text-zinc-600">
          How to book: "Open WebTrac" pre-fills the course, date, and time. Log in, press Search, and add the slot to your cart before it's taken.
        </div>
      )}
    </div>
  )
}
