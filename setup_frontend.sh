#!/bin/bash
# ============================================================
# Ozon Pro — Frontend Bootstrap Script
# ============================================================
# Создаёт полную структуру фронтенда в текущей директории.
# Запускать ИЗ КОРНЯ репозитория ozon-pro (рядом с docker-compose.yml).
#
# Использование на Mac:
#   cd ~/path/to/ozon-pro
#   bash setup_frontend.sh
#   git add frontend/ && git commit -m "feat: bootstrap frontend" && git push
# ============================================================

set -e

if [ ! -f "docker-compose.yml" ]; then
  echo "❌ Ошибка: запусти скрипт из корня репо ozon-pro (там где docker-compose.yml)"
  exit 1
fi

echo "📁 Создаю структуру frontend/..."
mkdir -p frontend/src/{components/ui,pages,lib,hooks,types,styles}

# ============================================================
# Корневые конфиги
# ============================================================

cat > frontend/.gitignore << 'EOF'
node_modules/
dist/
.env.local
.env.development.local
.env.production.local
*.log
.DS_Store
EOF

cat > frontend/.env.example << 'EOF'
# API URL — оставь пустым, чтобы фронт ходил на тот же хост через /api
VITE_API_URL=
EOF

cat > frontend/index.html << 'EOF'
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#ffffff" />
    <title>Ozon Pro — Финансовый мозг для селлеров</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
EOF

cat > frontend/postcss.config.js << 'EOF'
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
EOF

cat > frontend/tailwind.config.js << 'EOF'
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#ffffff',
        'bg-subtle': '#fafafa',
        surface: '#ffffff',
        border: {
          DEFAULT: '#e4e4e7',
          subtle: '#f4f4f5',
        },
        fg: {
          DEFAULT: '#09090b',
          muted: '#52525b',
          subtle: '#a1a1aa',
        },
        accent: {
          DEFAULT: '#18181b',
          hover: '#27272a',
        },
        success: '#16a34a',
        error: '#dc2626',
        warning: '#ca8a04',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        xs: ['12px', { lineHeight: '16px', letterSpacing: '0.01em' }],
        sm: ['13px', { lineHeight: '18px' }],
        base: ['14px', { lineHeight: '20px' }],
        lg: ['16px', { lineHeight: '24px' }],
        xl: ['18px', { lineHeight: '26px' }],
        '2xl': ['24px', { lineHeight: '32px', letterSpacing: '-0.01em' }],
        '3xl': ['32px', { lineHeight: '40px', letterSpacing: '-0.02em' }],
      },
      borderRadius: {
        sm: '6px',
        DEFAULT: '8px',
        md: '8px',
        lg: '12px',
      },
      animation: {
        'fade-in': 'fadeIn 200ms ease-out',
        'slide-up': 'slideUp 300ms ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
EOF

cat > frontend/tsconfig.json << 'EOF'
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
EOF

cat > frontend/tsconfig.node.json << 'EOF'
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
EOF

cat > frontend/vite.config.ts << 'EOF'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
})
EOF

cat > frontend/Dockerfile << 'EOF'
# ---- Build stage ----
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# ---- Serve stage ----
FROM nginx:1.27-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx-spa.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
EOF

cat > frontend/nginx-spa.conf << 'EOF'
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback — все маршруты ведут на index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Кэш для статики
    location ~* \.(js|css|png|jpg|jpeg|gif|svg|woff2?)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF

cat > frontend/package.json << 'EOF'
{
  "name": "ozon-pro-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2",
    "@tanstack/react-query": "^5.59.0",
    "axios": "^1.7.7",
    "lucide-react": "^0.445.0",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.5.2",
    "class-variance-authority": "^0.7.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.10",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.6.2",
    "vite": "^5.4.8",
    "tailwindcss": "^3.4.13",
    "postcss": "^8.4.47",
    "autoprefixer": "^10.4.20"
  }
}
EOF

# ============================================================
# src/main.tsx + App.tsx + globals.css
# ============================================================

cat > frontend/src/main.tsx << 'EOF'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './styles/globals.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
EOF

cat > frontend/src/App.tsx << 'EOF'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Login } from '@/pages/Login'
import { Register } from '@/pages/Register'
import { Dashboard } from '@/pages/Dashboard'
import { Cabinets } from '@/pages/Cabinets'
import { CabinetNew } from '@/pages/CabinetNew'
import { Settings } from '@/pages/Settings'
import { AppLayout } from '@/components/AppLayout'
import { ProtectedRoute } from '@/components/ProtectedRoute'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/cabinets" element={<Cabinets />} />
        <Route path="/cabinets/new" element={<CabinetNew />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
EOF

cat > frontend/src/styles/globals.css << 'EOF'
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  html, body {
    @apply bg-bg text-fg font-sans antialiased;
    font-feature-settings: 'cv11', 'ss01', 'ss03';
  }
  body {
    font-size: 14px;
    line-height: 20px;
  }
  *:focus-visible {
    @apply outline-none ring-2 ring-accent ring-offset-2 ring-offset-bg;
  }
  /* Custom scrollbar */
  ::-webkit-scrollbar {
    @apply w-2 h-2;
  }
  ::-webkit-scrollbar-track {
    @apply bg-transparent;
  }
  ::-webkit-scrollbar-thumb {
    @apply bg-border rounded-full;
  }
  ::-webkit-scrollbar-thumb:hover {
    @apply bg-fg-subtle;
  }
}

@layer utilities {
  .text-balance {
    text-wrap: balance;
  }
}
EOF

# ============================================================
# src/lib/ — utils, api client, auth
# ============================================================

cat > frontend/src/lib/utils.ts << 'EOF'
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(value: number, currency: string = 'RUB'): string {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value)
}

export function formatRelativeTime(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  const diff = Date.now() - d.getTime()
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return 'только что'
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min} мин назад`
  const hour = Math.floor(min / 60)
  if (hour < 24) return `${hour} ч назад`
  const day = Math.floor(hour / 24)
  if (day < 30) return `${day} дн назад`
  return d.toLocaleDateString('ru-RU')
}
EOF

cat > frontend/src/lib/api.ts << 'EOF'
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
EOF

cat > frontend/src/lib/auth.ts << 'EOF'
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
  // FastAPI OAuth2PasswordRequestForm ожидает form-data с username
  const formData = new URLSearchParams()
  formData.append('username', payload.email)
  formData.append('password', payload.password)
  const { data } = await api.post('/auth/login', formData, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
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
EOF

# ============================================================
# src/components/ui/ — базовые UI-кирпичики (shadcn-стиль)
# ============================================================

cat > frontend/src/components/ui/Button.tsx << 'EOF'
import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        primary:
          'bg-accent text-white hover:bg-accent-hover active:scale-[0.98]',
        secondary:
          'bg-bg border border-border text-fg hover:bg-bg-subtle active:scale-[0.98]',
        ghost: 'text-fg hover:bg-bg-subtle',
        danger: 'bg-error text-white hover:bg-red-700 active:scale-[0.98]',
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        md: 'h-9 px-4',
        lg: 'h-10 px-5 text-base',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, children, disabled, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? (
          <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
            <path d="M22 12a10 10 0 0 1-10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
          </svg>
        ) : null}
        {children}
      </button>
    )
  }
)
Button.displayName = 'Button'
EOF

cat > frontend/src/components/ui/Input.tsx << 'EOF'
import * as React from 'react'
import { cn } from '@/lib/utils'

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, hint, id, ...props }, ref) => {
    const inputId = id || React.useId()
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={inputId} className="text-sm font-medium text-fg">
            {label}
          </label>
        )}
        <input
          id={inputId}
          ref={ref}
          className={cn(
            'h-9 w-full rounded-md border bg-bg px-3 text-sm transition-colors',
            'placeholder:text-fg-subtle',
            'focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-bg focus:border-transparent',
            error
              ? 'border-error focus:ring-error'
              : 'border-border hover:border-fg-subtle',
            className
          )}
          {...props}
        />
        {hint && !error && <p className="text-xs text-fg-muted">{hint}</p>}
        {error && <p className="text-xs text-error">{error}</p>}
      </div>
    )
  }
)
Input.displayName = 'Input'
EOF

cat > frontend/src/components/ui/Card.tsx << 'EOF'
import * as React from 'react'
import { cn } from '@/lib/utils'

export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('rounded-lg border border-border bg-surface', className)}
      {...props}
    />
  )
)
Card.displayName = 'Card'

export const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('px-6 py-5 border-b border-border-subtle', className)} {...props} />
  )
)
CardHeader.displayName = 'CardHeader'

export const CardTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3 ref={ref} className={cn('text-lg font-semibold text-fg tracking-tight', className)} {...props} />
  )
)
CardTitle.displayName = 'CardTitle'

export const CardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn('text-sm text-fg-muted mt-1', className)} {...props} />
  )
)
CardDescription.displayName = 'CardDescription'

export const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('px-6 py-5', className)} {...props} />
  )
)
CardContent.displayName = 'CardContent'

export const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('px-6 py-4 border-t border-border-subtle', className)} {...props} />
  )
)
CardFooter.displayName = 'CardFooter'
EOF

cat > frontend/src/components/ui/Logo.tsx << 'EOF'
import { cn } from '@/lib/utils'

interface LogoProps {
  className?: string
  showText?: boolean
}

export function Logo({ className, showText = true }: LogoProps) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="w-7 h-7 rounded-md bg-accent flex items-center justify-center">
        <svg viewBox="0 0 16 16" className="w-4 h-4 text-white" fill="none">
          <path d="M2 4 L8 1 L14 4 L14 12 L8 15 L2 12 Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
          <path d="M8 1 L8 15" stroke="currentColor" strokeWidth="1.5" />
          <path d="M2 4 L8 7 L14 4" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
        </svg>
      </div>
      {showText && (
        <span className="font-semibold text-fg tracking-tight">Ozon Pro</span>
      )}
    </div>
  )
}
EOF

# ============================================================
# src/components/ — AppLayout + ProtectedRoute
# ============================================================

cat > frontend/src/components/ProtectedRoute.tsx << 'EOF'
import { Navigate } from 'react-router-dom'
import { isAuthenticated } from '@/lib/auth'

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}
EOF

cat > frontend/src/components/AppLayout.tsx << 'EOF'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { LayoutDashboard, Store, Settings as SettingsIcon, LogOut, ChevronDown } from 'lucide-react'
import { Logo } from './ui/Logo'
import { cn } from '@/lib/utils'
import { getCurrentUser, logout } from '@/lib/auth'
import { useState } from 'react'

const navItems = [
  { to: '/dashboard', label: 'Дашборд', icon: LayoutDashboard },
  { to: '/cabinets', label: 'Кабинеты', icon: Store },
  { to: '/settings', label: 'Настройки', icon: SettingsIcon },
]

export function AppLayout() {
  const navigate = useNavigate()
  const user = getCurrentUser()
  const [menuOpen, setMenuOpen] = useState(false)
  const initials = user?.email?.[0]?.toUpperCase() || 'U'

  return (
    <div className="min-h-screen bg-bg">
      {/* Topbar */}
      <header className="sticky top-0 z-30 bg-bg/80 backdrop-blur-md border-b border-border">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <Logo />
            <nav className="flex items-center gap-1">
              {navItems.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2 px-3 h-8 rounded-md text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-bg-subtle text-fg'
                        : 'text-fg-muted hover:text-fg hover:bg-bg-subtle'
                    )
                  }
                >
                  <Icon className="w-4 h-4" />
                  {label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="relative">
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="flex items-center gap-2 h-8 px-2 rounded-md hover:bg-bg-subtle transition-colors"
            >
              <div className="w-6 h-6 rounded-full bg-accent text-white text-xs font-medium flex items-center justify-center">
                {initials}
              </div>
              <span className="text-sm text-fg-muted hidden sm:inline">{user?.email}</span>
              <ChevronDown className="w-3.5 h-3.5 text-fg-subtle" />
            </button>
            {menuOpen && (
              <>
                <div className="fixed inset-0 z-30" onClick={() => setMenuOpen(false)} />
                <div className="absolute right-0 top-10 z-40 w-56 bg-surface border border-border rounded-lg shadow-lg overflow-hidden animate-fade-in">
                  <div className="px-3 py-2 border-b border-border-subtle">
                    <p className="text-xs text-fg-muted">Вошли как</p>
                    <p className="text-sm font-medium text-fg truncate">{user?.email}</p>
                  </div>
                  <button
                    onClick={() => {
                      setMenuOpen(false)
                      logout()
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-fg hover:bg-bg-subtle transition-colors"
                  >
                    <LogOut className="w-4 h-4" />
                    Выйти
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-6 py-8 animate-fade-in">
        <Outlet />
      </main>
    </div>
  )
}
EOF

# ============================================================
# src/pages/ — экраны приложения
# ============================================================

cat > frontend/src/pages/Login.tsx << 'EOF'
import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Logo } from '@/components/ui/Logo'
import { login } from '@/lib/auth'

export function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login({ email, password })
      navigate('/dashboard')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Не удалось войти. Проверь email и пароль.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm animate-slide-up">
        <div className="flex flex-col items-center mb-8">
          <Logo className="mb-6" />
          <h1 className="text-2xl font-semibold text-fg tracking-tight">Вход в аккаунт</h1>
          <p className="text-sm text-fg-muted mt-1.5">Введи email и пароль</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Input
            label="Email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
            autoFocus
          />
          <Input
            label="Пароль"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
          {error && (
            <div className="text-sm text-error bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {error}
            </div>
          )}
          <Button type="submit" loading={loading} className="w-full mt-2">
            Войти
          </Button>
        </form>

        <p className="text-sm text-fg-muted text-center mt-6">
          Нет аккаунта?{' '}
          <Link to="/register" className="text-fg font-medium hover:underline">
            Регистрация
          </Link>
        </p>
      </div>

      <footer className="absolute bottom-6 text-xs text-fg-subtle">
        Ozon Pro · Финансовый мозг для селлеров
      </footer>
    </div>
  )
}
EOF

cat > frontend/src/pages/Register.tsx << 'EOF'
import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Logo } from '@/components/ui/Logo'
import { register, login } from '@/lib/auth'

export function Register() {
  const navigate = useNavigate()
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
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Не удалось зарегистрироваться')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-bg px-4 py-12">
      <div className="w-full max-w-sm animate-slide-up">
        <div className="flex flex-col items-center mb-8">
          <Logo className="mb-6" />
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
EOF

cat > frontend/src/pages/Dashboard.tsx << 'EOF'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Store, TrendingUp, Package, ArrowUpRight, Plus } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, formatRelativeTime } from '@/lib/utils'
import { getCurrentUser } from '@/lib/auth'

interface DashboardData {
  cabinets_count: number
  total_revenue: number
  total_stock: number
  recent_activity: Array<{ id: string; cabinet_name: string; event: string; created_at: string }>
}

export function Dashboard() {
  const user = getCurrentUser()
  const { data, isLoading } = useQuery<DashboardData>({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const res = await api.get('/dashboard/')
      return res.data
    },
  })

  const stats = [
    {
      label: 'Кабинеты',
      value: data?.cabinets_count ?? 0,
      icon: Store,
      formatter: (v: number) => formatNumber(v),
    },
    {
      label: 'Оборот за 30 дней',
      value: data?.total_revenue ?? 0,
      icon: TrendingUp,
      formatter: (v: number) => formatCurrency(v),
    },
    {
      label: 'Остатки (шт)',
      value: data?.total_stock ?? 0,
      icon: Package,
      formatter: (v: number) => formatNumber(v),
    },
  ]

  const hasCabinets = (data?.cabinets_count ?? 0) > 0

  return (
    <div className="flex flex-col gap-8">
      {/* Header */}
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">
            Привет, {user?.full_name || user?.email?.split('@')[0]}
          </h1>
          <p className="text-sm text-fg-muted mt-1.5">
            Управление кабинетами Ozon и аналитика продаж
          </p>
        </div>
        {!hasCabinets && (
          <Link to="/cabinets/new">
            <Button>
              <Plus className="w-4 h-4" />
              Добавить кабинет
            </Button>
          </Link>
        )}
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {stats.map(({ label, value, icon: Icon, formatter }) => (
          <Card key={label} className="p-6 hover:border-fg-subtle transition-colors">
            <div className="flex items-start justify-between mb-3">
              <div className="w-9 h-9 rounded-md bg-bg-subtle flex items-center justify-center">
                <Icon className="w-4 h-4 text-fg-muted" />
              </div>
            </div>
            <p className="text-xs font-medium text-fg-muted uppercase tracking-wider">{label}</p>
            <p className="text-2xl font-semibold text-fg mt-1.5 tabular-nums">
              {isLoading ? <span className="inline-block w-20 h-7 bg-bg-subtle rounded animate-pulse" /> : formatter(value)}
            </p>
          </Card>
        ))}
      </div>

      {/* Empty state OR recent activity */}
      {!hasCabinets ? (
        <Card className="p-12 flex flex-col items-center text-center">
          <div className="w-14 h-14 rounded-full bg-bg-subtle flex items-center justify-center mb-4">
            <Store className="w-6 h-6 text-fg-muted" />
          </div>
          <h3 className="text-lg font-semibold text-fg">Пока нет кабинетов</h3>
          <p className="text-sm text-fg-muted mt-1.5 max-w-md">
            Подключи свой первый кабинет Ozon, чтобы получить аналитику по продажам, остаткам и финансам.
          </p>
          <Link to="/cabinets/new" className="mt-6">
            <Button>
              <Plus className="w-4 h-4" />
              Добавить кабинет Ozon
            </Button>
          </Link>
        </Card>
      ) : (
        <Card>
          <div className="px-6 py-4 border-b border-border-subtle flex items-center justify-between">
            <h2 className="text-base font-semibold text-fg">Последние действия</h2>
            <Link to="/cabinets" className="text-sm text-fg-muted hover:text-fg flex items-center gap-1">
              Все кабинеты <ArrowUpRight className="w-3.5 h-3.5" />
            </Link>
          </div>
          <ul className="divide-y divide-border-subtle">
            {(data?.recent_activity || []).map((item) => (
              <li key={item.id} className="px-6 py-3 flex items-center justify-between hover:bg-bg-subtle/50 transition-colors">
                <div className="flex items-center gap-3">
                  <div className="w-1.5 h-1.5 rounded-full bg-success" />
                  <span className="text-sm font-medium text-fg">{item.cabinet_name}</span>
                  <span className="text-sm text-fg-muted">{item.event}</span>
                </div>
                <span className="text-xs text-fg-subtle font-mono">{formatRelativeTime(item.created_at)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
EOF

cat > frontend/src/pages/Cabinets.tsx << 'EOF'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Plus, Store, RefreshCw } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'
import { formatRelativeTime } from '@/lib/utils'

interface Cabinet {
  id: string
  name: string
  ozon_client_id: string
  is_active: boolean
  last_sync_at?: string
  created_at: string
}

export function Cabinets() {
  const { data, isLoading } = useQuery<Cabinet[]>({
    queryKey: ['cabinets'],
    queryFn: async () => {
      const res = await api.get('/ozon-accounts/')
      return res.data
    },
  })

  const cabinets = data || []

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight">Кабинеты Ozon</h1>
          <p className="text-sm text-fg-muted mt-1.5">
            {cabinets.length > 0 ? `Подключено кабинетов: ${cabinets.length}` : 'Подключи свой первый кабинет'}
          </p>
        </div>
        <Link to="/cabinets/new">
          <Button>
            <Plus className="w-4 h-4" />
            Добавить кабинет
          </Button>
        </Link>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[1, 2].map((i) => (
            <Card key={i} className="p-6 animate-pulse">
              <div className="h-5 w-32 bg-bg-subtle rounded mb-2" />
              <div className="h-4 w-48 bg-bg-subtle rounded" />
            </Card>
          ))}
        </div>
      ) : cabinets.length === 0 ? (
        <Card className="p-12 flex flex-col items-center text-center">
          <div className="w-14 h-14 rounded-full bg-bg-subtle flex items-center justify-center mb-4">
            <Store className="w-6 h-6 text-fg-muted" />
          </div>
          <h3 className="text-lg font-semibold text-fg">Кабинеты не подключены</h3>
          <p className="text-sm text-fg-muted mt-1.5 max-w-md">
            Получи Client-Id и Api-Key в личном кабинете Ozon Seller (Настройки → Сертификаты API).
          </p>
          <Link to="/cabinets/new" className="mt-6">
            <Button>
              <Plus className="w-4 h-4" />
              Добавить первый кабинет
            </Button>
          </Link>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {cabinets.map((cab) => (
            <Card key={cab.id} className="p-6 hover:border-fg-subtle transition-all hover:shadow-sm">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-base font-semibold text-fg">{cab.name}</h3>
                  <p className="text-xs text-fg-muted font-mono mt-0.5">Client ID: {cab.ozon_client_id}</p>
                </div>
                <div className={`flex items-center gap-1.5 text-xs ${cab.is_active ? 'text-success' : 'text-fg-subtle'}`}>
                  <div className={`w-1.5 h-1.5 rounded-full ${cab.is_active ? 'bg-success' : 'bg-fg-subtle'}`} />
                  {cab.is_active ? 'Активен' : 'Отключён'}
                </div>
              </div>
              <div className="flex items-center justify-between pt-3 border-t border-border-subtle">
                <span className="text-xs text-fg-muted">
                  Последняя синхр.: {cab.last_sync_at ? formatRelativeTime(cab.last_sync_at) : 'не было'}
                </span>
                <button className="text-xs text-fg-muted hover:text-fg flex items-center gap-1 transition-colors">
                  <RefreshCw className="w-3 h-3" />
                  Синхронизировать
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
EOF

cat > frontend/src/pages/CabinetNew.tsx << 'EOF'
import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Card } from '@/components/ui/Card'
import { api } from '@/lib/api'

export function CabinetNew() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [clientId, setClientId] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.post('/ozon-accounts/', {
        name,
        ozon_client_id: clientId,
        ozon_api_key: apiKey,
      })
      navigate('/cabinets')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Не удалось добавить кабинет')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <Link to="/cabinets" className="inline-flex items-center gap-1 text-sm text-fg-muted hover:text-fg mb-6 transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Назад к списку
      </Link>

      <div className="mb-8">
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Подключить кабинет Ozon</h1>
        <p className="text-sm text-fg-muted mt-1.5">
          Введи Client-Id и Api-Key из личного кабинета Ozon Seller
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-8">
        <Card className="p-6">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <Input
              label="Название кабинета"
              placeholder="STOLZ KRAFT — основной"
              value={name}
              onChange={(e) => setName(e.target.value)}
              hint="Произвольное имя для удобства"
              required
              autoFocus
            />
            <Input
              label="Client ID"
              placeholder="12345"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              className="font-mono"
              required
            />
            <Input
              label="Api Key"
              type="password"
              placeholder="••••••••-••••-••••-••••-••••••••••••"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="font-mono"
              hint="Будет зашифрован при сохранении"
              required
            />
            {error && (
              <div className="text-sm text-error bg-red-50 border border-red-200 rounded-md px-3 py-2">
                {error}
              </div>
            )}
            <div className="flex items-center gap-3 mt-2">
              <Button type="submit" loading={loading}>
                Подключить кабинет
              </Button>
              <Link to="/cabinets">
                <Button type="button" variant="secondary">
                  Отмена
                </Button>
              </Link>
            </div>
          </form>
        </Card>

        <aside className="space-y-4">
          <Card className="p-5 bg-bg-subtle border-border-subtle">
            <h3 className="text-sm font-semibold text-fg mb-2">Где взять ключи?</h3>
            <ol className="text-xs text-fg-muted space-y-1.5 list-decimal list-inside">
              <li>Зайди в Ozon Seller</li>
              <li>Настройки → Сертификаты API</li>
              <li>Создай новый ключ с правами <span className="font-mono text-fg">Admin</span></li>
              <li>Скопируй Client-Id и Api-Key</li>
            </ol>
            <a
              href="https://seller.ozon.ru/app/settings/api-keys"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-accent font-medium mt-3 hover:underline"
            >
              Открыть Ozon Seller
              <ExternalLink className="w-3 h-3" />
            </a>
          </Card>
        </aside>
      </div>
    </div>
  )
}
EOF

cat > frontend/src/pages/Settings.tsx << 'EOF'
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
EOF

# ============================================================
# Финиш
# ============================================================

echo ""
echo "✅ Готово! Создано $(find frontend -type f | wc -l | xargs) файлов в frontend/"
echo ""
echo "Следующие шаги:"
echo "  1. git add frontend/"
echo "  2. git commit -m 'feat(frontend): add React+Vite+Tailwind premium UI'"
echo "  3. git push origin main"
echo ""
echo "После push скажи Claude — он подхватит деплой на сервере 🚀"
