import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Logo } from '@/components/ui/Logo'
import { AuthDecorPanel } from '@/components/ui/AuthDecorPanel'
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
    <div className="min-h-screen bg-bg lg:grid lg:grid-cols-2">
      {/* Left: form */}
      <div className="relative flex flex-col px-6 py-8 lg:px-12 lg:py-10 min-h-screen">
        <Logo />

        <div className="flex-1 flex items-center justify-center py-12">
          <div className="w-full max-w-sm animate-slide-up">
            <h1 className="text-3xl font-semibold text-fg tracking-tight">Вход в аккаунт</h1>
            <p className="text-sm text-fg-muted mt-2">Введи email и пароль, чтобы продолжить</p>

            <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-8">
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
              <Button type="submit" loading={loading} className="w-full mt-2 group">
                Войти
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
              </Button>
            </form>

            <p className="text-sm text-fg-muted text-center mt-8">
              Нет аккаунта?{' '}
              <Link to="/register" className="text-fg font-medium hover:underline underline-offset-4">
                Создать аккаунт
              </Link>
            </p>
          </div>
        </div>

        <footer className="flex items-center justify-between text-xs text-fg-subtle">
          <span>© 2026 Flowoi · Финансовый мозг для селлеров Ozon</span>
          <a href="#" className="hover:text-fg-muted transition-colors">Поддержка</a>
        </footer>
      </div>

      {/* Right: decor */}
      <AuthDecorPanel />
    </div>
  )
}
