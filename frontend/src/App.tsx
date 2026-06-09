import { BrowserRouter as Router, Routes, Route, Link, Navigate, useLocation } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { LoadingSkeleton } from './components/LoadingSkeleton'
import Dashboard from './pages/Dashboard'
import Watches from './pages/Watches'
import Notifications from './pages/Notifications'
import Login from './pages/Login'
import Signup from './pages/Signup'

const NAV = [
  { to: '/', label: 'Overview', title: 'Dashboard', icon: '◧' },
  { to: '/watches', label: 'Configure', title: 'Watches', icon: '◎' },
  { to: '/notifications', label: 'Activity', title: 'Opportunities', icon: '✦' },
]

function Shell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-screen bg-zinc-100 text-zinc-900">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex fixed left-0 top-0 h-screen w-64 border-r-2 border-black bg-zinc-200 flex-col z-20">
        <div className="border-b-2 border-black px-5 py-5">
          <div className="text-[10px] uppercase tracking-[0.22em] text-zinc-600">Austin, TX</div>
          <div className="mt-1 flex items-start justify-between">
            <div>
              <h1 className="text-3xl font-black leading-none">GOLF</h1>
              <p className="text-xl font-light tracking-wide">BOT</p>
            </div>
            <span className="text-xl leading-none">✦</span>
          </div>
        </div>

        <nav className="flex-1 px-4 py-4">
          <div className="mb-4 bg-black px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-white">Menu</div>
          <ul className="space-y-2">
            {NAV.map((n) => (
              <SideNavLink key={n.to} to={n.to} label={n.label}>{n.title}</SideNavLink>
            ))}
          </ul>
        </nav>

        <div className="border-t-2 border-black p-4">
          <div className="text-[10px] uppercase tracking-[0.18em] text-zinc-600">Signed in</div>
          <div className="mt-1 text-sm font-semibold truncate">{user?.email}</div>
          <button onClick={logout}
                  className="mt-3 w-full border-2 border-black bg-white px-2 py-1 text-[10px] uppercase tracking-[0.2em] hover:bg-zinc-300 focus:outline-none focus:ring-2 focus:ring-black focus:ring-offset-1">
            Sign out
          </button>
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="md:hidden sticky top-0 z-20 flex items-center justify-between border-b-2 border-black bg-zinc-200 px-4 py-3">
        <div className="flex items-baseline gap-2">
          <h1 className="text-2xl font-black leading-none">GOLF BOT</h1>
          <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-600">ATX</span>
        </div>
        <button onClick={logout}
                className="border-2 border-black bg-white px-2 py-1 text-[10px] uppercase tracking-[0.2em]">
          Sign out
        </button>
      </header>

      {/* Content */}
      <main className="md:ml-64 min-h-screen pb-20 md:pb-2">
        <div className="min-h-screen p-2">{children}</div>
      </main>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-20 grid grid-cols-3 border-t-2 border-black bg-zinc-200">
        {NAV.map((n) => (
          <BottomNavLink key={n.to} to={n.to} icon={n.icon} label={n.title} />
        ))}
      </nav>
    </div>
  )
}

function SideNavLink({ to, label, children }: { to: string; label: string; children: React.ReactNode }) {
  const location = useLocation()
  const isActive = location.pathname === to
  return (
    <li>
      <Link to={to} aria-current={isActive ? 'page' : undefined}
            className={`nav-item flex items-center justify-between border-2 px-3 py-3 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-black focus:ring-offset-1 ${
              isActive ? 'border-black bg-black text-white' : 'border-zinc-800 text-zinc-800 hover:bg-zinc-300'
            }`}>
        <span>
          <span className="block text-[10px] uppercase tracking-[0.16em] opacity-70">{label}</span>
          <span className="block text-sm font-semibold">{children}</span>
        </span>
        <span className="text-sm">→</span>
      </Link>
    </li>
  )
}

function BottomNavLink({ to, icon, label }: { to: string; icon: string; label: string }) {
  const location = useLocation()
  const isActive = location.pathname === to
  return (
    <Link to={to} aria-current={isActive ? 'page' : undefined}
          className={`flex flex-col items-center justify-center gap-0.5 py-2.5 text-[10px] uppercase tracking-[0.12em] ${
            isActive ? 'bg-black text-white' : 'text-zinc-700'
          }`}>
      <span className="text-base leading-none">{icon}</span>
      {label}
    </Link>
  )
}

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <LoadingSkeleton />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <Shell>{children}</Shell>
}

function PublicOnly({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <LoadingSkeleton />
  if (user) return <Navigate to="/" replace />
  return <>{children}</>
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
      <Route path="/signup" element={<PublicOnly><Signup /></PublicOnly>} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/watches" element={<Protected><Watches /></Protected>} />
      <Route path="/notifications" element={<Protected><Notifications /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Router>
        <AppRoutes />
        <Toaster position="top-right" toastOptions={{ style: { border: '2px solid black', borderRadius: 0 } }} />
      </Router>
    </AuthProvider>
  )
}
