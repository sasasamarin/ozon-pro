import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Logo } from '@/components/ui/Logo'
import { login } from '@/lib/auth'
import { getErrorMessage } from '@/lib/errors'

export function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login({ email, password })
      navigate('/dashboard')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm animate-slide-up">
        <div className="flex flex-col items-center mb-8">
          <Logo className="mb-6" />
          <h1 className="text-2xl font-semibold text-fg tracking-tight">Вход в аккаунт</h1>
          <p className="text-sm text-fg-muted mt-1.5">Введи email и пароль</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Input
            label="Email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
            autoFocus
          />
          <Input
            label="Пароль"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
          {error && (
            <div className="text-sm text-error bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {error}
            </div>
          )}
          <Button type="submit" loading={loading} className="w-full mt-2">
            Войти
          </Button>
        </form>

        <p className="text-sm text-fg-muted text-center mt-6">
          Нет аккаунта?{' '}
          <Link to="/register" className="text-fg font-medium hover:underline">
            Регистрация
          </Link>
        </p>
      </div>

      <footer className="absolute bottom-6 text-xs text-fg-subtle">
        Ozon Pro · Финансовый мозг для селлеров
      </footer>
    </div>
  )
}
