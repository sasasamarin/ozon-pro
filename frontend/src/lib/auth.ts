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
