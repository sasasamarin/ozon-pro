import { useState, useEffect } from 'react'
import { useNavigate, Link, useSearchParams, Navigate } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Logo } from '@/components/ui/Logo'
import { register, login } from '@/lib/auth'
import { getErrorMessage } from '@/lib/errors'

export function Register() {
  const navigate = useNavigate()
  const [params] = useSearchParams()

  // ВАЖНО: если на /register пришли с invite-токеном (старая ссылка
  // или ручной share invite_link), редиректим на /accept-invite чтобы
  // юзер НЕ создал новую компанию, а присоединился к существующей.
  const inviteToken = params.get('invite') || params.get('token')
  if (inviteToken) {
    return <Navigate to={`/accept-invite?token=${inviteToken}`} replace />
  }

  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await register({ email, password, full_name: fullName, company_name: companyName })
      await login({ email, password })
      navigate('/dashboard')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-bg px-4 py-12">
      <div className="w-full max-w-sm animate-slide-up">
        <div className="flex flex-col items-center mb-8">
          <Logo className="h-11 mb-6" />
          <h1 className="text-2xl font-semibold text-fg tracking-tight">Создать аккаунт</h1>
          <p className="text-sm text-fg-muted mt-1.5">Начни управлять кабинетами Ozon</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Input
            label="Имя"
            type="text"
            placeholder="Алексей"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
          />
          <Input
            label="Компания"
            type="text"
            placeholder="STOLZ KRAFT"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            required
          />
          <Input
            label="Email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
          <Input
            label="Пароль"
            type="password"
            placeholder="Минимум 8 символов"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
          />
          {error && (
            <div className="text-sm text-error bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {error}
            </div>
          )}
          <Button type="submit" loading={loading} className="w-full mt-2">
            Создать аккаунт
          </Button>
        </form>

        <p className="text-sm text-fg-muted text-center mt-6">
          Уже есть аккаунт?{' '}
          <Link to="/login" className="text-fg font-medium hover:underline">
            Войти
          </Link>
        </p>
      </div>
    </div>
  )
}
