import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Users, Plus, Copy, X, Loader2, Settings2, Trash2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  useCurrentUser,
  canManageTeam,
  roleLabel,
  ALL_MODULES,
} from '@/lib/auth'

interface MemberRow {
  id: string
  user_id: string
  email: string
  full_name: string | null
  role: string
  status: string
  accepted_at: string | null
  accessible_cabinet_ids: string[] | null
  allowed_modules: string[] | null
}

interface InvitationRow {
  id: string
  email: string
  role: string
  status: string
  expires_at: string
  invite_link: string
}

interface OzonAccountLite {
  id: string
  display_name?: string | null
  shop_name?: string | null
  client_id?: string | null
}

const ROLE_LABEL: Record<string, string> = {
  owner: 'Владелец',
  admin: 'Админ',
  manager: 'Менеджер',
  accountant: 'Бухгалтер',
  viewer: 'Только просмотр',
}

const ROLE_OPTIONS = ['admin', 'manager', 'accountant', 'viewer']

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
  const { data: cabinets } = useQuery<OzonAccountLite[]>({
    queryKey: ['ozon-accounts'],
    queryFn: async () => (await api.get('/ozon-accounts/')).data,
  })

  const { data: currentUser } = useCurrentUser()
  const canInvite = canManageTeam(currentUser?.role)

  const [email, setEmail] = useState('')
  const [role, setRole] = useState('manager')
  const [accessDialog, setAccessDialog] = useState<MemberRow | null>(null)

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

  const removeMember = useMutation({
    mutationFn: async (id: string) => api.delete(`/team/members/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team', 'members'] }),
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
                {ROLE_OPTIONS.map((r) => (
                  <option key={r} value={r}>{ROLE_LABEL[r]}</option>
                ))}
              </select>
            </div>
            <Button onClick={() => invite.mutate()} disabled={invite.isPending || !email}>
              {invite.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Пригласить
            </Button>
          </div>
          <p className="text-xs text-fg-muted mt-3">
            После принятия приглашения можно ограничить доступ к конкретным кабинетам и модулям
            кнопкой <b>«Доступ»</b> в таблице ниже.
          </p>
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
              <th className="py-2.5 px-4 font-medium">кабинеты</th>
              <th className="py-2.5 px-4 font-medium">модули</th>
              <th className="py-2.5 px-4 font-medium">статус</th>
              <th className="py-2.5 px-4 font-medium w-1"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {(members || []).map((m) => {
              const cabCount = m.accessible_cabinet_ids?.length
              const modCount = m.allowed_modules?.length
              const isOwner = m.role === 'owner'
              return (
                <tr key={m.id}>
                  <td className="py-2.5 px-4 font-mono text-fg">{m.email}</td>
                  <td className="py-2.5 px-4 text-fg">{m.full_name || '—'}</td>
                  <td className="py-2.5 px-4">
                    <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700">
                      {ROLE_LABEL[m.role] || m.role}
                    </span>
                  </td>
                  <td className="py-2.5 px-4 text-xs text-fg-muted">
                    {isOwner ? 'все' : (cabCount ? `${cabCount} шт.` : 'все')}
                  </td>
                  <td className="py-2.5 px-4 text-xs text-fg-muted">
                    {isOwner ? 'все' : (modCount ? `${modCount} шт.` : 'все')}
                  </td>
                  <td className="py-2.5 px-4 text-fg-muted">{m.status}</td>
                  <td className="py-2.5 px-4">
                    {canInvite && !isOwner && (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => setAccessDialog(m)}
                          className="px-2 py-1.5 rounded text-xs text-fg-muted hover:bg-bg-subtle inline-flex items-center gap-1"
                          title="Настроить доступ"
                        >
                          <Settings2 className="w-3.5 h-3.5" /> Доступ
                        </button>
                        <button
                          onClick={() => {
                            if (confirm(`Удалить ${m.email} из команды?`)) removeMember.mutate(m.id)
                          }}
                          className="p-1.5 text-fg-subtle hover:text-rose-700"
                          title="Удалить из команды"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              )
            })}
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

      {accessDialog && (
        <AccessDialog
          member={accessDialog}
          cabinets={cabinets || []}
          onClose={() => setAccessDialog(null)}
        />
      )}
    </div>
  )
}

/**
 * Диалог управления доступом сотрудника: роль + конкретные кабинеты + модули.
 * Пустой набор кабинетов = "ко всем" (легаси-семантика RBAC).
 */
function AccessDialog({
  member,
  cabinets,
  onClose,
}: {
  member: MemberRow
  cabinets: OzonAccountLite[]
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [role, setRole] = useState(member.role)
  const [allCabinets, setAllCabinets] = useState<boolean>(
    !member.accessible_cabinet_ids || member.accessible_cabinet_ids.length === 0,
  )
  const [cabIds, setCabIds] = useState<string[]>(member.accessible_cabinet_ids || [])
  const [allModules, setAllModules] = useState<boolean>(
    !member.allowed_modules || member.allowed_modules.length === 0,
  )
  const [modules, setModules] = useState<string[]>(member.allowed_modules || [])

  const save = useMutation({
    mutationFn: async () =>
      (await api.patch(`/team/members/${member.id}/access`, {
        role,
        accessible_cabinet_ids: allCabinets ? [] : cabIds,
        allowed_modules: allModules ? [] : modules,
      })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['team', 'members'] })
      onClose()
    },
  })

  const toggleCab = (id: string) =>
    setCabIds((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  const toggleMod = (slug: string) =>
    setModules((s) => (s.includes(slug) ? s.filter((x) => x !== slug) : [...s, slug]))

  // Группируем модули по category
  const groupedModules = ALL_MODULES.reduce<Record<string, typeof ALL_MODULES>>((acc, m) => {
    const g = m.group || 'Прочее'
    if (!acc[g]) acc[g] = []
    acc[g].push(m)
    return acc
  }, {})

  return (
    <div className="fixed inset-0 z-50 bg-fg/30 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-surface rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        <div className="px-6 py-4 border-b border-border-subtle flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-fg">Доступ для {member.email}</h3>
            <p className="text-xs text-fg-muted mt-0.5">
              Задай роль, конкретные кабинеты и модули
            </p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-bg-subtle">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-6">
          <section>
            <label className="block text-xs font-semibold text-fg mb-2 uppercase tracking-wider">Роль</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="h-9 px-3 rounded-md border border-border bg-surface text-sm w-full max-w-xs"
            >
              {ROLE_OPTIONS.map((r) => (
                <option key={r} value={r}>{ROLE_LABEL[r]}</option>
              ))}
            </select>
          </section>

          <section>
            <label className="flex items-center gap-2 text-xs font-semibold text-fg mb-2 uppercase tracking-wider">
              <span>Кабинеты Ozon</span>
            </label>
            <label className="flex items-center gap-2 text-sm mb-3">
              <input
                type="checkbox"
                checked={allCabinets}
                onChange={(e) => setAllCabinets(e.target.checked)}
                className="h-4 w-4 rounded border-border"
              />
              <span className="text-fg">Все кабинеты (текущие и будущие)</span>
            </label>
            {!allCabinets && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 pl-1">
                {cabinets.map((c) => (
                  <label
                    key={c.id}
                    className={cn(
                      'flex items-center gap-2 px-2.5 py-1.5 rounded-md text-sm border cursor-pointer',
                      cabIds.includes(c.id)
                        ? 'border-indigo-300 bg-indigo-50/50'
                        : 'border-border-subtle hover:bg-bg-subtle',
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={cabIds.includes(c.id)}
                      onChange={() => toggleCab(c.id)}
                      className="h-4 w-4 rounded border-border"
                    />
                    <span className="truncate">
                      {c.display_name || c.shop_name || c.client_id || c.id.slice(0, 8)}
                    </span>
                  </label>
                ))}
                {cabinets.length === 0 && (
                  <p className="text-xs text-fg-muted col-span-full">Нет подключённых кабинетов.</p>
                )}
              </div>
            )}
          </section>

          <section>
            <label className="block text-xs font-semibold text-fg mb-2 uppercase tracking-wider">
              Модули приложения
            </label>
            <label className="flex items-center gap-2 text-sm mb-3">
              <input
                type="checkbox"
                checked={allModules}
                onChange={(e) => setAllModules(e.target.checked)}
                className="h-4 w-4 rounded border-border"
              />
              <span className="text-fg">Все модули</span>
            </label>
            {!allModules && (
              <div className="flex flex-col gap-3 pl-1">
                {Object.entries(groupedModules).map(([groupName, mods]) => (
                  <div key={groupName}>
                    <div className="text-[10px] uppercase tracking-wider text-fg-subtle mb-1">{groupName}</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                      {mods.map((m) => (
                        <label
                          key={m.slug}
                          className={cn(
                            'flex items-center gap-2 px-2.5 py-1.5 rounded-md text-sm border cursor-pointer',
                            modules.includes(m.slug)
                              ? 'border-indigo-300 bg-indigo-50/50'
                              : 'border-border-subtle hover:bg-bg-subtle',
                          )}
                        >
                          <input
                            type="checkbox"
                            checked={modules.includes(m.slug)}
                            onChange={() => toggleMod(m.slug)}
                            className="h-4 w-4 rounded border-border"
                          />
                          <span className="truncate">{m.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        <div className="px-6 py-4 border-t border-border-subtle flex items-center justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Отмена</Button>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            Сохранить
          </Button>
        </div>
      </div>
    </div>
  )
}
