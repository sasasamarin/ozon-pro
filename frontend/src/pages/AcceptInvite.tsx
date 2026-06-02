/**
 * /accept-invite?token=XXX — публичная (без auth) страница.
 * Принимает приглашение в команду: создаёт User + CompanyMember,
 * возвращает JWT → auto-login → редирект на /dashboard.
 */
import { useState } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Loader2, ShieldCheck, AlertCircle, Mail } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'

interface InvitePreview {
  email: string
  role: string
  company_name: string
  expires_at: string
  already_user: boolean
}

interface AcceptResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export function AcceptInvite() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const navigate = useNavigate()

  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { data: preview, isLoading, error: previewErr } = useQuery<InvitePreview>({
    queryKey: ['invite-preview', token],
    queryFn: async () =>
      (await api.get(`/team/invitations/preview/${token}`)).data,
    enabled: !!token,
    retry: false,
  })

  const accept = useMutation<AcceptResponse>({
    mutationFn: async () => {
      const r = await api.post('/team/invitations/accept', {
        token,
        full_name: fullName,
        password,
      })
      return r.data
    },
    onSuccess: (data) => {
      localStorage.setItem('flowoi_token', data.access_token)
      // лёгкая полная перезагрузка — query-кеши обнулятся, App перечитает /auth/me
      window.location.href = '/dashboard'
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      setError(detail || 'Ошибка принятия приглашения')
    },
  })

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="p-6 max-w-md w-full text-center">
          <AlertCircle className="size-10 mx-auto text-rose-500 mb-3" />
          <h2 className="text-lg font-semibold text-fg">Ссылка повреждена</h2>
          <p className="text-sm text-fg-muted mt-1">
            В ссылке нет токена приглашения. Попросите повторно прислать приглашение.
          </p>
        </Card>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="size-6 animate-spin text-fg-muted" />
      </div>
    )
  }

  if (previewErr || !preview) {
    const msg =
      (previewErr as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      || 'Приглашение недействительно'
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="p-6 max-w-md w-full text-center">
          <AlertCircle className="size-10 mx-auto text-amber-500 mb-3" />
          <h2 className="text-lg font-semibold text-fg">Ссылка не работает</h2>
          <p className="text-sm text-fg-muted mt-2">{msg}</p>
          <p className="text-xs text-fg-muted mt-3">
            Попросите администратора прислать новое приглашение.
          </p>
          <Link to="/login" className="block mt-4 text-sm text-fg hover:underline">
            Уже есть аккаунт? Войти →
          </Link>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg p-4">
      <Card className="p-6 max-w-md w-full">
        <div className="text-center mb-5">
          <ShieldCheck className="size-12 mx-auto text-emerald-500 mb-2" />
          <h1 className="text-2xl font-semibold text-fg">Приглашение в команду</h1>
          <p className="text-sm text-fg-muted mt-2">Вас приглашают в компанию</p>
          <p className="text-xl font-semibold text-fg mt-1">«{preview.company_name}»</p>
          <p className="text-xs text-fg-muted mt-1">
            Роль: <b>{preview.role}</b> · Email: <b>{preview.email}</b>
          </p>
        </div>

        {preview.already_user ? (
          <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm text-blue-900 mb-4">
            <Mail className="size-4 inline mr-1" />
            Этот email <b>уже зарегистрирован</b> в Flowoi. Компания будет добавлена
            к вашему аккаунту. Пароль не изменится — введите любой ≥ 8 символов
            (он используется только если аккаунта ещё не было).
          </div>
        ) : (
          <div className="bg-emerald-50 border border-emerald-200 rounded p-3 text-sm text-emerald-900 mb-4">
            Новый аккаунт будет создан. Придумайте пароль ≥ 8 символов.
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="text-xs text-fg-muted block mb-1">Ваше имя</label>
            <input
              value={fullName} onChange={(e) => setFullName(e.target.value)}
              placeholder="Например: Лариса"
              className="w-full px-3 py-2 border border-border-subtle rounded text-sm bg-bg"
            />
          </div>
          <div>
            <label className="text-xs text-fg-muted block mb-1">Пароль</label>
            <input
              type="password" value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="минимум 8 символов"
              className="w-full px-3 py-2 border border-border-subtle rounded text-sm bg-bg"
            />
          </div>
        </div>

        {error && <p className="text-sm text-rose-600 mt-3">{error}</p>}

        <button
          onClick={() => accept.mutate()}
          disabled={fullName.length < 2 || password.length < 8 || accept.isPending}
          className="w-full mt-5 py-2 bg-fg text-white rounded font-medium hover:opacity-90 disabled:opacity-50"
        >
          {accept.isPending ? 'Принимаю...' : 'Принять приглашение'}
        </button>

        <p className="text-xs text-fg-muted text-center mt-4">
          <Link to="/login" className="hover:underline">Уже есть аккаунт? Войти</Link>
        </p>
      </Card>
    </div>
  )
}
