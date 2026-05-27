import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { getCurrentUser, logout } from '@/lib/auth'

export function Settings() {
  const user = getCurrentUser()

  return (
    <div className="max-w-3xl">
      <div className="mb-8">
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Настройки</h1>
        <p className="text-sm text-fg-muted mt-1.5">Профиль и параметры аккаунта</p>
      </div>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Профиль</CardTitle>
            <CardDescription>Информация об аккаунте</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Input label="Email" value={user?.email || ''} disabled />
            <Input label="Имя" placeholder="Твоё имя" defaultValue={user?.full_name || ''} />
            <Button>Сохранить изменения</Button>
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
