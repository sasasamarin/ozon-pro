import axios from 'axios'

const baseURL = import.meta.env.VITE_API_URL || '/api/v1'

export const api = axios.create({
  baseURL,
  timeout: 15000,
})

// Подставляем JWT токен из localStorage в каждый запрос
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('ozon_pro_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// При 401 — разлогиниваем и редиректим
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('ozon_pro_token')
      localStorage.removeItem('ozon_pro_user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)
