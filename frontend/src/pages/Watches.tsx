import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { api, apiErrorMessage, Course, Watch, WatchInput } from '../api/client'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { ConfirmModal } from '../components/ConfirmModal'

const DAYS: { code: string; label: string }[] = [
  { code: 'mon', label: 'Mon' },
  { code: 'tue', label: 'Tue' },
  { code: 'wed', label: 'Wed' },
  { code: 'thu', label: 'Thu' },
  { code: 'fri', label: 'Fri' },
  { code: 'sat', label: 'Sat' },
  { code: 'sun', label: 'Sun' },
]

const DEFAULT_FORM: WatchInput = {
  label: 'My watch',
  num_players: 4,
  num_holes: 18,
  course_ids: 'all',
  target_days: 'sat,sun',
  window_start: '07:00',
  window_end: '11:00',
  active: true,
}

function formatTime(t: string): string {
  const [h, m] = t.split(':').map(Number)
  const ampm = h >= 12 ? 'pm' : 'am'
  const hr = h % 12 === 0 ? 12 : h % 12
  return `${hr}:${String(m).padStart(2, '0')} ${ampm}`
}

const shortCourse = (name: string) => name.replace(' Golf Course', '')

const toMinutes = (t: string): number => {
  const [h, m] = t.split(':').map(Number)
  return h * 60 + m
}

const courseSet = (csv: string, all: Course[]): Set<number> =>
  csv === 'all'
    ? new Set(all.map((c) => c.id))
    : new Set(csv.split(',').filter(Boolean).map(Number))

/**
 * Whether two watches can match the same tee time.
 *
 * Player count is deliberately ignored: a slot with four openings satisfies a
 * 2-player and a 4-player watch alike, so it still counts as an overlap.
 */
function watchesOverlap(draft: WatchInput, existing: Watch, all: Course[]): boolean {
  if (draft.num_holes !== existing.num_holes) return false

  const draftDays = new Set(draft.target_days.split(',').filter(Boolean))
  if (!existing.target_days.split(',').some((d) => draftDays.has(d))) return false

  const draftCourses = courseSet(draft.course_ids, all)
  if (![...courseSet(existing.course_ids, all)].some((id) => draftCourses.has(id))) return false

  return (
    toMinutes(draft.window_start) <= toMinutes(existing.window_end) &&
    toMinutes(existing.window_start) <= toMinutes(draft.window_end)
  )
}

export default function Watches() {
  const navigate = useNavigate()
  const [watches, setWatches] = useState<Watch[]>([])
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [form, setForm] = useState<WatchInput>(DEFAULT_FORM)
  const [courseMode, setCourseMode] = useState<'all' | 'specific'>('all')
  const [selectedCourses, setSelectedCourses] = useState<Set<number>>(new Set())
  const [pendingDelete, setPendingDelete] = useState<Watch | null>(null)

  useEffect(() => {
    load()
  }, [])

  const load = async () => {
    try {
      const [w, c] = await Promise.all([api.getWatches(), api.getCourses()])
      setWatches(w.data)
      setCourses(c.data)
    } catch {
      toast.error('Failed to load watches')
    } finally {
      setLoading(false)
    }
  }

  const selectedDays = useMemo(
    () => new Set(form.target_days.split(',').filter(Boolean)),
    [form.target_days],
  )

  const toggleDay = (code: string) => {
    const next = new Set(selectedDays)
    next.has(code) ? next.delete(code) : next.add(code)
    setForm({ ...form, target_days: DAYS.filter((d) => next.has(d.code)).map((d) => d.code).join(',') })
  }

  const toggleCourse = (id: number) => {
    const next = new Set(selectedCourses)
    next.has(id) ? next.delete(id) : next.add(id)
    setSelectedCourses(next)
  }

  const resolvedCourseIds = () =>
    courseMode === 'all' ? 'all' : [...selectedCourses].sort((a, b) => a - b).join(',')

  const summary = useMemo(() => {
    const players = `${form.num_players} player${form.num_players === 1 ? '' : 's'}`
    const days = form.target_days
      ? DAYS.filter((d) => selectedDays.has(d.code)).map((d) => d.label).join(' / ')
      : 'no days'
    const courseText =
      courseMode === 'all'
        ? 'any course'
        : selectedCourses.size === 0
          ? 'no course selected'
          : [...selectedCourses].map((id) => shortCourse(courses.find((c) => c.id === id)?.name || `${id}`)).join(', ')
    return `Find ${players} for ${form.num_holes} holes at ${courseText} on ${days} between ${formatTime(form.window_start)} and ${formatTime(form.window_end)}.`
  }, [form, selectedDays, courseMode, selectedCourses, courses])

  const overlapping = useMemo(() => {
    const courseIds =
      courseMode === 'all' ? 'all' : [...selectedCourses].sort((a, b) => a - b).join(',')
    if (!form.target_days || (courseMode === 'specific' && selectedCourses.size === 0)) return []
    const draft: WatchInput = { ...form, course_ids: courseIds }
    return watches.filter((w) => w.active && watchesOverlap(draft, w, courses))
  }, [form, courseMode, selectedCourses, watches, courses])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.target_days) return toast.error('Pick at least one day')
    if (form.window_start >= form.window_end) return toast.error('End time must be after start time')
    if (courseMode === 'specific' && selectedCourses.size === 0)
      return toast.error('Select at least one course (or choose All courses)')
    setSubmitting(true)
    try {
      await api.createWatch({ ...form, course_ids: resolvedCourseIds() })
      toast.success('Watch created')
      setForm(DEFAULT_FORM)
      setCourseMode('all')
      setSelectedCourses(new Set())
      load()
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Failed to create watch'))
    } finally {
      setSubmitting(false)
    }
  }

  const toggleActive = async (w: Watch) => {
    try {
      await api.updateWatch(w.id, { active: !w.active })
      setWatches((prev) => prev.map((x) => (x.id === w.id ? { ...x, active: !x.active } : x)))
    } catch {
      toast.error('Failed to update watch')
    }
  }

  const confirmDelete = async () => {
    if (!pendingDelete) return
    const w = pendingDelete
    setPendingDelete(null)
    try {
      await api.deleteWatch(w.id)
      setWatches((prev) => prev.filter((x) => x.id !== w.id))
      toast.success('Watch deleted')
    } catch {
      toast.error('Failed to delete watch')
    }
  }

  const runScan = async () => {
    setScanning(true)
    try {
      const res = await api.scanNow()
      if (res.data.new_matches > 0) {
        toast.success(`${res.data.new_matches} new match(es) found`)
        navigate('/notifications')
      } else {
        toast(res.data.message)
      }
    } catch {
      toast.error('Scan failed')
    } finally {
      setScanning(false)
    }
  }

  const courseLabel = (csv: string) =>
    csv === 'all'
      ? 'All courses'
      : csv.split(',').map((id) => shortCourse(courses.find((c) => c.id === Number(id))?.name || id)).join(', ')

  const segBtn = (active: boolean) =>
    `border-2 border-black px-3 py-2 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-black focus:ring-offset-1 ${
      active ? 'bg-black text-white' : 'bg-white hover:bg-zinc-100'
    }`

  if (loading) return <LoadingSkeleton />

  return (
    <div className="p-4 md:p-8 space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-3xl md:text-4xl font-black">Watches</h2>
          <p className="text-zinc-700 mt-1 text-sm">
            Get an email the moment a tee time opens in your window. Scans every 5 min, Tue 6am - Sun night.
          </p>
        </div>
        <button className="button" onClick={runScan} disabled={scanning}>
          {scanning ? 'Scanning...' : 'Scan now'}
        </button>
      </div>

      {/* Create form */}
      <form onSubmit={handleCreate} className="page-card p-5 md:p-6 space-y-5">
        <h3 className="text-xl font-bold">New watch</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="watch-label" className="block text-[10px] uppercase tracking-[0.16em] text-zinc-600 mb-1">Label</label>
            <input id="watch-label" className="input w-full" value={form.label}
                   onChange={(e) => setForm({ ...form, label: e.target.value })} />
          </div>
          <div>
            <span className="block text-[10px] uppercase tracking-[0.16em] text-zinc-600 mb-1">Holes</span>
            <div className="flex gap-2">
              {[18, 9].map((h) => (
                <button key={h} type="button" aria-pressed={form.num_holes === h}
                        onClick={() => setForm({ ...form, num_holes: h })}
                        className={segBtn(form.num_holes === h)}>
                  {h}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div>
          <span className="block text-[10px] uppercase tracking-[0.16em] text-zinc-600 mb-1">Players needed</span>
          <div className="flex gap-2">
            {[1, 2, 3, 4].map((n) => (
              <button key={n} type="button" aria-pressed={form.num_players === n}
                      onClick={() => setForm({ ...form, num_players: n })}
                      className={`${segBtn(form.num_players === n)} w-12`}>
                {n}
              </button>
            ))}
          </div>
        </div>

        <div>
          <span className="block text-[10px] uppercase tracking-[0.16em] text-zinc-600 mb-1">Days</span>
          <div className="flex flex-wrap gap-2">
            {DAYS.map((d) => (
              <button key={d.code} type="button" aria-pressed={selectedDays.has(d.code)}
                      onClick={() => toggleDay(d.code)}
                      className={segBtn(selectedDays.has(d.code))}>
                {d.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 max-w-sm">
          <div>
            <label htmlFor="watch-from" className="block text-[10px] uppercase tracking-[0.16em] text-zinc-600 mb-1">From</label>
            <input id="watch-from" className="input w-full" type="time" value={form.window_start}
                   onChange={(e) => setForm({ ...form, window_start: e.target.value })} />
          </div>
          <div>
            <label htmlFor="watch-to" className="block text-[10px] uppercase tracking-[0.16em] text-zinc-600 mb-1">To</label>
            <input id="watch-to" className="input w-full" type="time" value={form.window_end}
                   onChange={(e) => setForm({ ...form, window_end: e.target.value })} />
          </div>
        </div>

        <div>
          <span className="block text-[10px] uppercase tracking-[0.16em] text-zinc-600 mb-1">Courses</span>
          <div className="flex gap-2 mb-2">
            <button type="button" aria-pressed={courseMode === 'all'}
                    onClick={() => setCourseMode('all')} className={segBtn(courseMode === 'all')}>
              All courses
            </button>
            <button type="button" aria-pressed={courseMode === 'specific'}
                    onClick={() => setCourseMode('specific')} className={segBtn(courseMode === 'specific')}>
              Specific courses
            </button>
          </div>
          {courseMode === 'specific' && (
            <div className="flex flex-wrap gap-2">
              {courses.map((c) => (
                <button key={c.id} type="button" aria-pressed={selectedCourses.has(c.id)}
                        onClick={() => toggleCourse(c.id)} className={segBtn(selectedCourses.has(c.id))}>
                  {shortCourse(c.name)}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="border-2 border-black bg-zinc-100 p-3 text-sm">
          <span className="text-[10px] uppercase tracking-[0.16em] text-zinc-600 block mb-1">Summary</span>
          {summary}
        </div>

        {overlapping.length > 0 && (
          <div className="border-2 border-black bg-amber-100 p-3 text-sm" role="status">
            <span className="text-[10px] uppercase tracking-[0.16em] text-zinc-700 block mb-1">
              Overlaps an existing watch
            </span>
            This matches the same tee times as{' '}
            <span className="font-bold">
              {overlapping.map((w) => w.label).join(', ')}
            </span>
            . You'll still get a single email per opening, but the same slot will be
            listed once per watch in your notifications. Widening{' '}
            {overlapping.length === 1 ? 'that watch' : 'one of those watches'} instead
            usually keeps things cleaner.
          </div>
        )}

        <button className="button" type="submit" disabled={submitting}>
          {submitting ? 'Creating...' : 'Create watch'}
        </button>
      </form>

      {/* List */}
      <div className="space-y-3">
        <h3 className="text-xl font-bold">Your watches ({watches.length})</h3>
        {watches.length === 0 ? (
          <div className="page-card p-6 text-zinc-600 text-sm">No watches yet. Create one above.</div>
        ) : (
          watches.map((w) => (
            <div key={w.id} className="page-card list-item p-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold">{w.label}</span>
                  <span className={`text-[10px] uppercase tracking-[0.16em] px-2 py-0.5 border-2 border-black ${w.active ? 'bg-black text-white' : 'bg-white text-zinc-600'}`}>
                    {w.active ? 'Active' : 'Paused'}
                  </span>
                </div>
                <div className="text-sm text-zinc-700 mt-1">
                  {w.target_days.split(',').map((d) => DAYS.find((x) => x.code === d)?.label).join(', ')}
                  {' · '}{formatTime(w.window_start)} - {formatTime(w.window_end)}
                  {' · '}{w.num_players}p · {w.num_holes} holes
                </div>
                <div className="text-xs text-zinc-500 mt-0.5">{courseLabel(w.course_ids)}</div>
              </div>
              <div className="flex items-center gap-2">
                <button className="border-2 border-black px-3 py-2 text-xs font-semibold uppercase bg-white hover:bg-zinc-200 focus:outline-none focus:ring-2 focus:ring-black"
                        onClick={() => toggleActive(w)}>
                  {w.active ? 'Pause' : 'Resume'}
                </button>
                <button className="border-2 border-black px-3 py-2 text-xs font-semibold uppercase bg-white hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-black"
                        onClick={() => setPendingDelete(w)}>
                  Delete
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      <ConfirmModal
        isOpen={pendingDelete !== null}
        title="Delete watch"
        message={`Delete "${pendingDelete?.label}"? This can't be undone.`}
        confirmText="Delete"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
