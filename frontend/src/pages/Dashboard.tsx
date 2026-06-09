import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, FoundSlot, ScanStatus, Watch } from '../api/client'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { useAuth } from '../auth/AuthContext'
import { timeAgo, timeUntil } from '../lib/time'

export default function Dashboard() {
  const { user } = useAuth()
  const [watches, setWatches] = useState<Watch[] | null>(null)
  const [slots, setSlots] = useState<FoundSlot[] | null>(null)
  const [status, setStatus] = useState<ScanStatus | null>(null)
  const [errors, setErrors] = useState<{ watches?: boolean; slots?: boolean; status?: boolean }>({})
  const [loading, setLoading] = useState(true)

  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null)

  const loadStatus = () =>
    api
      .getScanStatus()
      .then((r) => {
        setStatus(r.data)
        setRefreshedAt(new Date())
        setErrors((e) => ({ ...e, status: false }))
      })
      .catch(() => setErrors((e) => ({ ...e, status: true })))

  useEffect(() => {
    // Load each section independently so one failure does not blank the page.
    Promise.allSettled([
      api.getWatches().then((r) => setWatches(r.data)).catch(() => setErrors((e) => ({ ...e, watches: true }))),
      api.getFoundSlots(6).then((r) => setSlots(r.data)).catch(() => setErrors((e) => ({ ...e, slots: true }))),
      loadStatus(),
    ]).finally(() => setLoading(false))

    // Keep scanner health live without reloading the whole page.
    const interval = setInterval(loadStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  if (loading) return <LoadingSkeleton />

  const activeWatches = watches?.filter((w) => w.active).length ?? 0
  const scannerOn = status?.scheduler_running
  const scanHealthy = scannerOn && !status?.last_scan.message.startsWith('Scan error')

  return (
    <div className="p-4 md:p-8 space-y-6">
      <div>
        <h2 className="text-3xl md:text-4xl font-black">Dashboard</h2>
        <p className="text-zinc-700 mt-1 text-sm">Welcome back, {user?.name}.</p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="page-card p-6">
          <div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">Active watches</div>
          <div className="text-4xl font-black mt-2">{errors.watches ? '—' : activeWatches}</div>
          <div className="text-xs text-zinc-500 mt-1">
            {errors.watches ? 'Failed to load' : `${watches?.length ?? 0} total`}
          </div>
        </div>

        <div className="page-card p-6">
          <div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">Scanner</div>
          <div className="flex items-center gap-2 mt-2">
            <span className={`inline-block h-3 w-3 border-2 border-black ${scanHealthy ? 'bg-green-500' : scannerOn ? 'bg-yellow-400' : 'bg-zinc-400'}`} />
            <span className="text-2xl font-black">
              {errors.status ? '—' : scannerOn ? (status?.in_window ? 'Live' : 'Idle') : 'Off'}
            </span>
          </div>
          <div className="text-xs text-zinc-500 mt-1">
            {status?.in_window ? 'In scan window' : 'Outside window'} · next {timeUntil(status?.next_run)}
          </div>
        </div>

        <div className="page-card p-6">
          <div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">Recent finds</div>
          <div className="text-4xl font-black mt-2">{errors.slots ? '—' : slots?.length ?? 0}</div>
          <div className="text-xs text-zinc-500 mt-1">
            <Link to="/notifications" className="underline">View all</Link>
          </div>
        </div>
      </div>

      {/* Scanner health detail */}
      <div className="page-card p-5 md:p-6">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xl font-bold">Scanner health</h3>
          {refreshedAt && (
            <span className="text-[10px] uppercase tracking-[0.16em] text-zinc-500">
              Live · updated {refreshedAt.toLocaleTimeString()}
            </span>
          )}
        </div>
        {errors.status ? (
          <div className="text-sm text-red-700">Couldn't load scanner status. The API may be down.</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <Stat label="Last scan" value={timeAgo(status?.last_scan.at)} />
            <Stat label="Next run" value={timeUntil(status?.next_run)} />
            <Stat label="Dates scanned" value={String(status?.last_scan.dates_scanned.length ?? 0)} />
            <Stat label="Last result" value={status?.last_scan.message ?? '—'} small />
          </div>
        )}
      </div>

      {/* Latest finds */}
      <div className="page-card p-5 md:p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-bold">Latest finds</h3>
          <Link to="/watches" className="button">Manage watches</Link>
        </div>
        {errors.slots ? (
          <div className="text-sm text-red-700">Couldn't load recent finds.</div>
        ) : (slots?.length ?? 0) === 0 ? (
          <div className="text-zinc-600 text-sm">
            No tee times found yet.{' '}
            {(watches?.length ?? 0) === 0 && (
              <>Create a <Link to="/watches" className="underline font-semibold">watch</Link> to get started.</>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            {slots!.map((s) => (
              <div key={s.id} className="border-2 border-black p-3 bg-white flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold truncate">{s.course_name}</div>
                  <div className="text-sm text-zinc-700">{s.date} · {s.time} · {s.open_slots} open</div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-xs text-zinc-500 hidden sm:inline">{timeAgo(s.found_at)}</span>
                  <a className="button" href={s.booking_url} target="_blank" rel="noopener noreferrer">Book</a>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value, small }: { label: string; value: string; small?: boolean }) {
  return (
    <div className="border-2 border-black bg-zinc-100 p-3">
      <div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">{label}</div>
      <div className={`font-semibold ${small ? 'text-xs mt-1' : 'text-lg'}`}>{value}</div>
    </div>
  )
}
