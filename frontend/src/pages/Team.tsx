import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Users, Plus, Copy, X, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useCurrentUser, canManageTeam, roleLabel } from '@/lib/auth'

interface MemberRow {
  id: string
  user_id: string
  email: string
  full_name: string | null
  role: string
  status: string
  accepted_at: string | null
}

interface InvitationRow {
  id: string
  email: string
  role: string
  status: string
  expires_at: string
  invite_link: string
}

const ROLE_LABEL: Record<string, string> = {
  owner: 'Владелец',
  admin: 'Админ',
  manager: 'Менеджер',
  accountant: 'Бухгалтер',
  viewer: 'Только просмотр',
}

export function Team() {
  const qc = useQueryClient()
  const { data: members } = useQuery<MemberRow[]>({
    queryKey: ['team', 'members'],
    queryFn: async () => (await api.get('/team/members')).data,
  })
  const { data: invitations } = useQuery<InvitationRow[]>({
    queryKey: ['team', 'invitations'],
    queryFn: async () => (await api.get('/team/invitations')).data,
  })

  const { data: currentUser } = useCurrentUser()
  const canInvite = canManageTeam(currentUser?.role)

  const [email, setEmail] = useState('')
  const [role, setRole] = useState('manager')

  const invite = useMutation({
    mutationFn: async () => (await api.post('/team/invitations', { email, role })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['team'] })
      setEmail('')
    },
  })

  const revoke = useMutation({
    mutationFn: async (id: string) => api.delete(`/team/invitations/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team', 'invitations'] }),
  })

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Команда</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          {members?.length ?? 0} участников · {invitations?.length ?? 0} приглашений в ожидании
        </p>
      </div>

      {canInvite ? (
        <Card className="p-5">
          <h3 className="text-base font-semibold text-fg mb-3">Пригласить участника</h3>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Email</label>
              <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email@company.ru" />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-fg-muted uppercase mb-1">Роль</label>
              <select value={role} onChange={(e) => setRole(e.target.value)}
                className="h-9 px-3 rounded-md border border-border bg-surface text-sm">
                <option value="admin">Админ</option>
                <option value="manager">Менеджер</option>
                <option value="accountant">Бухгалтер</option>
                <option value="viewer">Только просмотр</option>
              </select>
            </div>
            <Button onClick={() => invite.mutate()} disabled={invite.isPending || !email}>
              {invite.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Пригласить
            </Button>
          </div>
        </Card>
      ) : (
        <Card className="p-4 bg-amber-50/50 border-amber-200 text-sm text-amber-800">
          У вашей роли (<b>{roleLabel(currentUser?.role)}</b>) нет прав приглашать участников.
          Попросите владельца или администратора компании.
        </Card>
      )}

      <Card className="overflow-hidden">
        <div className="px-6 py-4 border-b border-border-subtle">
          <h2 className="text-base font-semibold text-fg flex items-center gap-2">
            <Users className="w-4 h-4 text-fg-muted" />
            Участники
          </h2>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-bg-subtle/50 border-b border-border-subtle">
            <tr className="text-left text-xs text-fg-muted uppercase tracking-wider">
              <th className="py-2.5 px-4 font-medium">email</th>
              <th className="py-2.5 px-4 font-medium">имя</th>
              <th className="py-2.5 px-4 font-medium">роль</th>
              <th className="py-2.5 px-4 font-medium">статус</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {(members || []).map((m) => (
              <tr key={m.id}>
                <td className="py-2.5 px-4 font-mono text-fg">{m.email}</td>
                <td className="py-2.5 px-4 text-fg">{m.full_name || '—'}</td>
                <td className="py-2.5 px-4">
                  <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700">
                    {ROLE_LABEL[m.role] || m.role}
                  </span>
                </td>
                <td className="py-2.5 px-4 text-fg-muted">{m.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {(invitations?.length ?? 0) > 0 && (
        <Card className="overflow-hidden">
          <div className="px-6 py-4 border-b border-border-subtle">
            <h2 className="text-base font-semibold text-fg">Приглашения в ожидании</h2>
          </div>
          <ul className="divide-y divide-border-subtle">
            {invitations!.map((inv) => (
              <li key={inv.id} className="px-6 py-3 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-fg">{inv.email}</div>
                  <div className="text-xs text-fg-muted">
                    Роль: {ROLE_LABEL[inv.role] || inv.role} · истекает {new Date(inv.expires_at).toLocaleDateString('ru-RU')}
                  </div>
                </div>
                <button
                  onClick={() => {
                    navigator.clipboard?.writeText(window.location.origin + inv.invite_link)
                  }}
                  className="px-2 py-1.5 rounded text-xs text-fg-muted hover:bg-bg-subtle inline-flex items-center gap-1"
                >
                  <Copy className="w-3.5 h-3.5" /> Ссылка
                </button>
                <button
                  onClick={() => revoke.mutate(inv.id)}
                  className="p-1.5 text-fg-subtle hover:text-rose-700"
                >
                  <X className="w-4 h-4" />
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
