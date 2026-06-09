import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { apiErrorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'

export default function Signup() {
  const { signup } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (password.length < 8) {
      toast.error('Password must be at least 8 characters')
      return
    }
    setSubmitting(true)
    try {
      await signup(name, email, password)
      navigate('/')
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Signup failed'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md page-card p-8">
        <div className="text-[10px] uppercase tracking-[0.22em] text-zinc-600">Austin, TX</div>
        <h1 className="text-4xl font-black leading-none mt-1">GOLF BOT</h1>
        <p className="mt-2 text-sm text-zinc-700">Create an account to start watching for tee times.</p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label htmlFor="signup-name" className="block text-[10px] uppercase tracking-[0.16em] text-zinc-600 mb-1">Name</label>
            <input id="signup-name" className="input w-full" type="text" value={name} required
                   autoComplete="name" onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label htmlFor="signup-email" className="block text-[10px] uppercase tracking-[0.16em] text-zinc-600 mb-1">Email</label>
            <input id="signup-email" className="input w-full" type="email" value={email} required
                   autoComplete="email" onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label htmlFor="signup-password" className="block text-[10px] uppercase tracking-[0.16em] text-zinc-600 mb-1">
              Password (min 8 chars)
            </label>
            <input id="signup-password" className="input w-full" type="password" value={password} required
                   autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />
          </div>
          <button className="button w-full" type="submit" disabled={submitting}>
            {submitting ? 'Creating...' : 'Create Account'}
          </button>
        </form>

        <p className="mt-4 text-sm text-zinc-700">
          Already have an account? <Link to="/login" className="font-semibold underline">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
