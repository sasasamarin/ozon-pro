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
