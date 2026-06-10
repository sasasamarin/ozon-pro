import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api'

export interface CurrentUser {
  id: string
  email: string
  full_name: string | null
  company_id: string
  company_name: string | null
  role: string
  is_admin: boolean
  /** Список ozon_account_id, к которым у пользователя есть доступ. NULL = ко всем. */
  accessible_cabinet_ids?: string[] | null
  /** Список slug-модулей. NULL = все модули доступны. */
  allowed_modules?: string[] | null
}

export interface LoginPayload {
  email: string
  password: string
}

export interface RegisterPayload {
  email: string
  password: string
  full_name?: string
  company_name?: string
}

export async function login(payload: LoginPayload) {
  const { data } = await api.post('/auth/login', payload)
  localStorage.setItem('flowoi_token', data.access_token)
  return data
}

export async function register(payload: RegisterPayload) {
  const { data } = await api.post('/auth/register', payload)
  if (data.access_token) {
    localStorage.setItem('flowoi_token', data.access_token)
  }
  return data
}

export function logout() {
  localStorage.removeItem('flowoi_token')
  // Legacy ключ от ранних версий — на всякий случай чистим
  localStorage.removeItem('flowoi_user')
  window.location.href = '/login'
}

export function isAuthenticated(): boolean {
  return !!localStorage.getItem('flowoi_token')
}

/**
 * Реальная подгрузка текущего юзера через GET /api/v1/auth/me.
 * Один запрос на App-load, кэш в react-query → доступен везде через хук.
 */
export function useCurrentUser() {
  return useQuery<CurrentUser>({
    queryKey: ['current-user'],
    queryFn: async () => {
      const res = await api.get('/auth/me')
      return res.data
    },
    enabled: isAuthenticated(),
    staleTime: 5 * 60 * 1000, // 5 минут
  })
}

export function useUpdateProfile() {
  const qc = useQueryClient()
  return async (payload: { full_name?: string }) => {
    const res = await api.patch('/auth/me', payload)
    qc.setQueryData(['current-user'], res.data)
    return res.data as CurrentUser
  }
}


// === RBAC helpers (синхронизированы с backend/app/api/deps_rbac.py) ===

export const ROLE_OWNER = 'owner'
export const ROLE_ADMIN = 'admin'
export const ROLE_MANAGER = 'manager'
export const ROLE_ACCOUNTANT = 'accountant'
export const ROLE_VIEWER = 'viewer'

export function canManageTeam(role?: string): boolean {
  return role === ROLE_OWNER || role === ROLE_ADMIN
}

export function canManageCabinets(role?: string): boolean {
  return role === ROLE_OWNER || role === ROLE_ADMIN
}

export function canDeleteCabinet(role?: string): boolean {
  return role === ROLE_OWNER
}

export function canManageFinance(role?: string): boolean {
  return role === ROLE_OWNER || role === ROLE_ADMIN || role === ROLE_ACCOUNTANT
}

export function canManageOperations(role?: string): boolean {
  return role === ROLE_OWNER || role === ROLE_ADMIN || role === ROLE_MANAGER
}

export function isReadOnly(role?: string): boolean {
  return role === ROLE_VIEWER
}

export function roleLabel(role?: string): string {
  switch (role) {
    case ROLE_OWNER: return 'Владелец'
    case ROLE_ADMIN: return 'Администратор'
    case ROLE_MANAGER: return 'Менеджер'
    case ROLE_ACCOUNTANT: return 'Бухгалтер'
    case ROLE_VIEWER: return 'Наблюдатель'
    default: return role || '—'
  }
}


// === Каталог модулей (для управления доступом) ===
// Slug должен совпадать с backend-проверкой в deps_rbac.require_module().
export interface ModuleDef {
  slug: string
  label: string
  group?: string
}

export const ALL_MODULES: ModuleDef[] = [
  { slug: 'dashboard',     label: 'Дашборд',                group: 'Главное' },
  { slug: 'analytics',     label: 'Аналитика',              group: 'Главное' },
  { slug: 'sales-plan',    label: 'План продаж',            group: 'Главное' },
  { slug: 'products',      label: 'Товары',                 group: 'Операции' },
  { slug: 'orders',        label: 'Заказы',                 group: 'Операции' },
  { slug: 'finance',       label: 'Финансы и P&L',          group: 'Финансы' },
  { slug: 'procurement',   label: 'Закупки',                group: 'Операции' },
  { slug: 'loans',         label: 'Кредиты',                group: 'Финансы' },
  { slug: 'alerts',        label: 'Маркеры и алерты',       group: 'Главное' },
  { slug: 'ai',            label: 'AI-чат и Telegram',      group: 'Главное' },
  { slug: 'cabinets',      label: 'Кабинеты Ozon',          group: 'Настройки' },
  { slug: 'team',          label: 'Команда',                group: 'Настройки' },
  { slug: 'integrations',  label: 'Интеграции',             group: 'Настройки' },
  { slug: 'settings',      label: 'Профиль и настройки',    group: 'Настройки' },
]

/** Доступен ли пользователю конкретный модуль. */
export function hasModule(user: CurrentUser | undefined | null, slug: string): boolean {
  if (!user) return false
  // OWNER/ADMIN — всегда всё
  if (user.role === ROLE_OWNER || user.role === ROLE_ADMIN) return true
  // NULL/undefined = без ограничения
  if (!user.allowed_modules) return true
  return user.allowed_modules.includes(slug)
}

/** Есть ли у пользователя доступ к конкретному ozon_account_id. */
export function hasCabinetAccess(user: CurrentUser | undefined | null, cabinetId: string): boolean {
  if (!user) return false
  if (user.role === ROLE_OWNER || user.role === ROLE_ADMIN) return true
  if (!user.accessible_cabinet_ids) return true
  return user.accessible_cabinet_ids.includes(cabinetId)
}
