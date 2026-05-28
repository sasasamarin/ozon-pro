import { useEffect, useState } from 'react'
import { CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { HelpHint } from '@/components/ui/HelpHint'
import { logout, useCurrentUser, useUpdateProfile } from '@/lib/auth'
import { getErrorMessage } from '@/lib/errors'

type SaveState =
  | { kind: 'idle' }
  | { kind: 'saving' }
  | { kind: 'ok' }
  | { kind: 'error'; message: string }

export function Settings() {
  const { data: user, isLoading } = useCurrentUser()
  const updateProfile = useUpdateProfile()

  const [fullName, setFullName] = useState('')
  const [save, setSave] = useState<SaveState>({ kind: 'idle' })

  useEffect(() => {
    if (user) {
      setFullName(user.full_name || '')
    }
  }, [user])

  const dirty = !!user && (fullName.trim() !== (user.full_name || ''))

  async function handleSave() {
    if (!dirty) return
    setSave({ kind: 'saving' })
    try {
      await updateProfile({ full_name: fullName.trim() })
      setSave({ kind: 'ok' })
    } catch (err) {
      setSave({ kind: 'error', message: getErrorMessage(err) })
    }
  }

  return (
    <div className="max-w-3xl">
      <div className="mb-8">
        <div className="flex items-center gap-2">
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Настройки</h1>
          <HelpHint text="Профиль и параметры аккаунта. Имя видно команде. Email — главный идентификатор входа, смена требует подтверждения нового адреса (скоро). Здесь же — кнопка выхода с текущего устройства." />
        </div>
        <p className="text-sm text-fg-muted mt-1.5">Профиль и параметры аккаунта</p>
      </div>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Профиль</CardTitle>
            <CardDescription>
              {user?.company_name ? `Компания: ${user.company_name}` : 'Информация об аккаунте'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Input
              label="Email"
              value={isLoading ? 'Загрузка…' : (user?.email || '')}
              disabled
              hint="Смена email пока недоступна — будет с подтверждением нового адреса."
            />
            <Input
              label="Имя"
              placeholder="Твоё имя"
              value={fullName}
              onChange={(e) => {
                setFullName(e.target.value)
                if (save.kind !== 'idle') setSave({ kind: 'idle' })
              }}
              disabled={isLoading}
            />
            <div className="flex items-center gap-3">
              <Button onClick={handleSave} disabled={!dirty || save.kind === 'saving'}>
                {save.kind === 'saving' && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Сохранить изменения
              </Button>
              {save.kind === 'ok' && (
                <span className="inline-flex items-center gap-1.5 text-xs text-success">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Сохранено
                </span>
              )}
              {save.kind === 'error' && (
                <span className="inline-flex items-start gap-1.5 text-xs text-error">
                  <AlertCircle className="w-3.5 h-3.5 mt-0.5" />
                  <span className="break-all">{save.message}</span>
                </span>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Сессия</CardTitle>
            <CardDescription>Выйти из аккаунта на этом устройстве</CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="secondary" onClick={logout}>
              Выйти из аккаунта
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
