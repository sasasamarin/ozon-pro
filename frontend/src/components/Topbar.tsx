import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { Menu, ChevronDown, Plus, Store, LogOut, Check } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { getCurrentUser, logout } from '@/lib/auth'
import { useCabinetStore, type OzonAccountSummary } from '@/stores/cabinet'

interface TopbarProps {
  onOpenSidebar: () => void
}

export function Topbar({ onOpenSidebar }: TopbarProps) {
  const navigate = useNavigate()
  const user = getCurrentUser()
  const initials = user?.email?.[0]?.toUpperCase() || 'U'

  const { selectedCabinetId, setSelectedCabinetId } = useCabinetStore()
  const [cabinetMenuOpen, setCabinetMenuOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  const cabinetRef = useRef<HTMLDivElement>(null)
  const userRef = useRef<HTMLDivElement>(null)

  const { data: cabinets = [], isLoading } = useQuery<OzonAccountSummary[]>({
    queryKey: ['ozon-accounts'],
    queryFn: async () => {
      const res = await api.get('/ozon-accounts/')
      return res.data
    },
  })

  // Auto-select first cabinet when list loads and nothing is selected
  useEffect(() => {
    if (!selectedCabinetId && cabinets.length > 0) {
      setSelectedCabinetId(cabinets[0].id)
    }
    if (selectedCabinetId && cabinets.length > 0 && !cabinets.find((c) => c.id === selectedCabinetId)) {
      setSelectedCabinetId(cabinets[0].id)
    }
  }, [cabinets, selectedCabinetId, setSelectedCabinetId])

  // Close dropdowns on outside click
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (cabinetRef.current && !cabinetRef.current.contains(e.target as Node)) {
        setCabinetMenuOpen(false)
      }
      if (userRef.current && !userRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const selectedCabinet = cabinets.find((c) => c.id === selectedCabinetId)

  return (
    <header className="sticky top-0 z-30 bg-bg/80 backdrop-blur-md border-b border-border-subtle">
      <div className="h-14 flex items-center justify-between gap-3 px-4 sm:px-6">
        <div className="flex items-center gap-2 min-w-0">
          {/* Mobile hamburger */}
          <button
            type="button"
            onClick={onOpenSidebar}
            className="lg:hidden p-1.5 -ml-1.5 rounded-md text-fg-muted hover:bg-bg-subtle"
            aria-label="Открыть меню"
          >
            <Menu className="w-5 h-5" />
          </button>

          {/* Cabinet switcher */}
          <div ref={cabinetRef} className="relative min-w-0">
            {cabinets.length === 0 && !isLoading ? (
              <Link
                to="/cabinets/new"
                className="inline-flex items-center gap-2 h-9 px-3 rounded-md border border-border bg-bg hover:bg-bg-subtle text-sm font-medium text-fg transition-colors"
              >
                <Plus className="w-4 h-4" />
                Подключи первый кабинет
              </Link>
            ) : (
              <button
                type="button"
                onClick={() => setCabinetMenuOpen((o) => !o)}
                className="inline-flex items-center gap-2 h-9 px-2.5 rounded-md border border-border-subtle bg-bg hover:bg-bg-subtle text-sm font-medium text-fg transition-colors max-w-[220px] sm:max-w-[280px]"
                disabled={isLoading}
              >
                <Store className="w-4 h-4 text-fg-muted shrink-0" />
                <span className="truncate">
                  {isLoading
                    ? 'Загрузка...'
                    : selectedCabinet?.name || 'Выбери кабинет'}
                </span>
                <ChevronDown className="w-3.5 h-3.5 text-fg-subtle shrink-0" />
              </button>
            )}

            {cabinetMenuOpen && cabinets.length > 0 && (
              <div className="absolute left-0 top-11 z-40 w-[280px] bg-surface border border-border rounded-lg shadow-elev overflow-hidden animate-fade-in">
                <div className="px-3 py-2 border-b border-border-subtle">
                  <p className="text-[10px] font-semibold text-fg-subtle uppercase tracking-wider">
                    Кабинеты
                  </p>
                </div>
                <ul className="max-h-[300px] overflow-y-auto py-1">
                  {cabinets.map((c) => (
                    <li key={c.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedCabinetId(c.id)
                          setCabinetMenuOpen(false)
                        }}
                        className={cn(
                          'w-full flex items-center gap-2 px-3 py-2 text-left text-sm hover:bg-bg-subtle transition-colors',
                          c.id === selectedCabinetId ? 'text-fg' : 'text-fg-muted'
                        )}
                      >
                        <Store className="w-4 h-4 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="truncate font-medium">{c.name}</div>
                          <div className="text-[11px] text-fg-subtle">
                            {c.status} · {c.has_performance_api ? 'PA подключён' : 'только Seller API'}
                          </div>
                        </div>
                        {c.id === selectedCabinetId && (
                          <Check className="w-4 h-4 text-success shrink-0" />
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  onClick={() => {
                    setCabinetMenuOpen(false)
                    navigate('/cabinets/new')
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2.5 text-sm font-medium text-fg border-t border-border-subtle hover:bg-bg-subtle transition-colors"
                >
                  <Plus className="w-4 h-4" />
                  Добавить кабинет
                </button>
              </div>
            )}
          </div>
        </div>

        {/* User menu */}
        <div ref={userRef} className="relative">
          <button
            type="button"
            onClick={() => setUserMenuOpen((o) => !o)}
            className="flex items-center gap-2 h-9 px-2 rounded-md hover:bg-bg-subtle transition-colors"
          >
            <div className="w-6 h-6 rounded-full bg-accent text-white text-xs font-medium flex items-center justify-center">
              {initials}
            </div>
            <span className="text-sm text-fg-muted hidden sm:inline truncate max-w-[160px]">
              {user?.email}
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-fg-subtle" />
          </button>
          {userMenuOpen && (
            <div className="absolute right-0 top-11 z-40 w-56 bg-surface border border-border rounded-lg shadow-elev overflow-hidden animate-fade-in">
              <div className="px-3 py-2 border-b border-border-subtle">
                <p className="text-xs text-fg-muted">Вошли как</p>
                <p className="text-sm font-medium text-fg truncate">{user?.email}</p>
              </div>
              <button
                onClick={() => {
                  setUserMenuOpen(false)
                  logout()
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-fg hover:bg-bg-subtle transition-colors"
              >
                <LogOut className="w-4 h-4" />
                Выйти
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
