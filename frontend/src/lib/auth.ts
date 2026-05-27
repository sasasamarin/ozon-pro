import { api } from './api'

export interface User {
  id: string
  email: string
  full_name?: string
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
  localStorage.setItem('ozon_pro_token', data.access_token)
  if (data.user) {
    localStorage.setItem('ozon_pro_user', JSON.stringify(data.user))
  }
  return data
}

export async function register(payload: RegisterPayload) {
  const { data } = await api.post('/auth/register', payload)
  return data
}

export function logout() {
  localStorage.removeItem('ozon_pro_token')
  localStorage.removeItem('ozon_pro_user')
  window.location.href = '/login'
}

export function getCurrentUser(): User | null {
  const raw = localStorage.getItem('ozon_pro_user')
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function isAuthenticated(): boolean {
  return !!localStorage.getItem('ozon_pro_token')
}
