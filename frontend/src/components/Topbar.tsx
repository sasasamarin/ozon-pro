import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import {
  Menu,
  ChevronDown,
  Plus,
  Store,
  LogOut,
  Check,
  CheckSquare,
  Square,
  Megaphone,
} from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { logout, useCurrentUser } from '@/lib/auth'
import { useCabinetStore, type OzonAccountSummary } from '@/stores/cabinet'
import { Logo } from './ui/Logo'

interface TopbarProps {
  onOpenSidebar: () => void
}

function pluralizeCabinets(n: number): string {
  const mod100 = n % 100
  if (mod100 >= 11 && mod100 <= 14) return 'кабинетов'
  const mod10 = n % 10
  if (mod10 === 1) return 'кабинет'
  if (mod10 >= 2 && mod10 <= 4) return 'кабинета'
  return 'кабинетов'
}

export function Topbar({ onOpenSidebar }: TopbarProps) {
  const navigate = useNavigate()
  const { data: user } = useCurrentUser()
  const initials = user?.email?.[0]?.toUpperCase() || 'U'

  const { selectedCabinetIds, toggleCabinetId, selectAll } = useCabinetStore()
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
    refetchOnMount: 'always',
    staleTime: 0,
  })

  // Если в selected попал ID удалённого кабинета — выпиливаем
  useEffect(() => {
    if (selectedCabinetIds.length === 0 || cabinets.length === 0) return
    const valid = new Set(cabinets.map((c) => c.id))
    const cleaned = selectedCabinetIds.filter((id) => valid.has(id))
    if (cleaned.length !== selectedCabinetIds.length) {
      useCabinetStore.getState().setSelectedCabinetIds(cleaned)
    }
  }, [cabinets, selectedCabinetIds])

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

  // Label для кнопки переключателя
  const allSelected = selectedCabinetIds.length === 0
  const selectedCabinets = cabinets.filter((c) => selectedCabinetIds.includes(c.id))
  let buttonLabel = 'Все кабинеты'
  if (!allSelected) {
    if (selectedCabinets.length === 1) {
      buttonLabel = selectedCabinets[0].name
    } else if (selectedCabinets.length === 2) {
      buttonLabel = `${selectedCabinets[0].name} +1`
    } else {
      buttonLabel = `${selectedCabinets.length} ${pluralizeCabinets(selectedCabinets.length)}`
    }
  }

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

          {/* Mobile-only logo */}
          <Link to="/dashboard" className="lg:hidden">
            <Logo className="h-7" />
          </Link>

          {/* Cabinet multi-switcher */}
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
                aria-haspopup="listbox"
                aria-expanded={cabinetMenuOpen}
              >
                <Store className="w-4 h-4 text-fg-muted shrink-0" />
                <span className="truncate">
                  {isLoading ? 'Загрузка…' : buttonLabel}
                </span>
                <ChevronDown className="w-3.5 h-3.5 text-fg-subtle shrink-0" />
              </button>
            )}

            {cabinetMenuOpen && cabinets.length > 0 && (
              <div
                className="absolute left-0 top-11 z-40 w-[320px] bg-surface border border-border rounded-lg shadow-elev overflow-hidden animate-fade-in"
                role="listbox"
                aria-multiselectable="true"
              >
                <div className="px-3 py-2 border-b border-border-subtle flex items-center justify-between">
                  <p className="text-[10px] font-semibold text-fg-subtle uppercase tracking-wider">
                    Кабинеты ({cabinets.length})
                  </p>
                  {!allSelected && (
                    <button
                      type="button"
                      onClick={selectAll}
                      className="text-[11px] text-fg-muted hover:text-fg transition-colors"
                    >
                      Сбросить
                    </button>
                  )}
                </div>

                {/* «Все кабинеты» в качестве первой опции */}
                <button
                  type="button"
                  onClick={selectAll}
                  className={cn(
                    'w-full flex items-center gap-3 px-3 py-2.5 text-left text-sm border-b border-border-subtle hover:bg-bg-subtle transition-colors',
                    allSelected ? 'text-fg' : 'text-fg-muted',
                  )}
                >
                  {allSelected ? (
                    <CheckSquare className="w-4 h-4 text-accent shrink-0" />
                  ) : (
                    <Square className="w-4 h-4 text-fg-subtle shrink-0" />
                  )}
                  <span className="font-medium">Все кабинеты</span>
                </button>

                <ul className="max-h-[320px] overflow-y-auto py-1">
                  {cabinets.map((c) => {
                    const checked = !allSelected && selectedCabinetIds.includes(c.id)
                    return (
                      <li key={c.id}>
                        <button
                          type="button"
                          onClick={() => toggleCabinetId(c.id)}
                          className={cn(
                            'w-full flex items-center gap-3 px-3 py-2 text-left text-sm hover:bg-bg-subtle transition-colors',
                            checked ? 'text-fg' : 'text-fg-muted',
                          )}
                        >
                          {checked ? (
                            <CheckSquare className="w-4 h-4 text-accent shrink-0" />
                          ) : (
                            <Square className="w-4 h-4 text-fg-subtle shrink-0" />
                          )}
                          <Store className="w-4 h-4 shrink-0 -ml-0.5" />
                          <div className="flex-1 min-w-0">
                            <div className="truncate font-medium flex items-center gap-1.5">
                              {c.name}
                              {c.has_performance_api && (
                                <Megaphone
                                  className="w-3 h-3 text-fg-subtle"
                                  aria-label="Performance API подключён"
                                />
                              )}
                            </div>
                            <div className="text-[11px] text-fg-subtle">
                              {c.status === 'active' ? 'Активен' : c.status === 'error' ? 'Ошибка' : c.status}
                            </div>
                          </div>
                          {checked && <Check className="w-4 h-4 text-success shrink-0" />}
                        </button>
                      </li>
                    )
                  })}
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
              {user?.email || '…'}
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-fg-subtle" />
          </button>
          {userMenuOpen && (
            <div className="absolute right-0 top-11 z-40 w-64 bg-surface border border-border rounded-lg shadow-elev overflow-hidden animate-fade-in">
              <div className="px-3 py-2 border-b border-border-subtle">
                <p className="text-xs text-fg-muted">Вошли как</p>
                <p className="text-sm font-medium text-fg truncate">{user?.email || '—'}</p>
                {user?.full_name && (
                  <p className="text-xs text-fg-muted truncate mt-0.5">{user.full_name}</p>
                )}
                {user?.company_name && (
                  <p className="text-[11px] text-fg-subtle truncate mt-0.5">
                    {user.company_name}
                  </p>
                )}
              </div>
              <Link
                to="/settings"
                onClick={() => setUserMenuOpen(false)}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-fg hover:bg-bg-subtle transition-colors border-b border-border-subtle"
              >
                Настройки
              </Link>
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
