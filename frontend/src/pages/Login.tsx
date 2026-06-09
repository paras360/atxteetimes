import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import toast from 'react-hot-toast'
import { apiErrorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from || '/'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await login(email, password)
      navigate(from, { replace: true })
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Login failed'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md page-card p-8">
        <div className="text-[10px] uppercase tracking-[0.22em] text-zinc-600">Austin, TX</div>
        <h1 className="text-4xl font-black leading-none mt-1">GOLF BOT</h1>
        <p className="mt-2 text-sm text-zinc-700">Sign in to manage your tee-time watches.</p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label htmlFor="login-email" className="block text-[10px] uppercase tracking-[0.16em] text-zinc-600 mb-1">Email</label>
            <input id="login-email" className="input w-full" type="email" value={email} required
                   autoComplete="email" onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label htmlFor="login-password" className="block text-[10px] uppercase tracking-[0.16em] text-zinc-600 mb-1">Password</label>
            <input id="login-password" className="input w-full" type="password" value={password} required
                   autoComplete="current-password" onChange={(e) => setPassword(e.target.value)} />
          </div>
          <button className="button w-full" type="submit" disabled={submitting}>
            {submitting ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <p className="mt-4 text-sm text-zinc-700">
          No account? <Link to="/signup" className="font-semibold underline">Create one</Link>
        </p>
      </div>
    </div>
  )
}
