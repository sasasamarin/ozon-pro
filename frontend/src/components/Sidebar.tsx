import { NavLink, Link } from 'react-router-dom'
import { Zap, Lock, X, ExternalLink } from 'lucide-react'
import { Logo } from './ui/Logo'
import { cn } from '@/lib/utils'
import { NAV_GROUPS, FOOTER_NAV, type NavItem } from '@/lib/menu'

// TODO: replace with real user tier when account context exposes it
const HAS_PREMIUM_PLUS = false

function ItemBadge({ item }: { item: NavItem }) {
  if (item.badge === 'killer') {
    return (
      <span className="ml-auto inline-flex items-center justify-center w-4 h-4 rounded-md bg-gradient-to-br from-violet-100 to-indigo-100 text-violet-600 shrink-0">
        <Zap className="w-2.5 h-2.5" strokeWidth={2.5} />
      </span>
    )
  }
  if (item.badge === 'premium' && !HAS_PREMIUM_PLUS) {
    return <Lock className="ml-auto w-3 h-3 text-fg-subtle shrink-0" />
  }
  if (item.badge === 'ai') {
    return (
      <span className="ml-auto text-[9px] font-bold leading-none px-1.5 py-0.5 rounded bg-violet-50 text-violet-600 tracking-wider shrink-0">
        AI
      </span>
    )
  }
  return null
}

function SidebarItem({ item, onNavigate }: { item: NavItem; onNavigate?: () => void }) {
  const { icon: Icon } = item
  const baseClasses =
    'flex items-center gap-2.5 h-8 px-2.5 rounded-md text-sm font-medium transition-colors'

  if (item.externalUrl) {
    return (
      <a
        href={item.externalUrl}
        target="_blank"
        rel="noopener noreferrer"
        onClick={onNavigate}
        className={cn(baseClasses, 'text-fg-muted hover:bg-bg-subtle hover:text-fg')}
      >
        <Icon className="w-4 h-4 shrink-0" strokeWidth={1.75} />
        <span className="truncate">{item.label}</span>
        <ExternalLink className="ml-auto w-3 h-3 text-fg-subtle shrink-0" />
      </a>
    )
  }

  return (
    <NavLink
      to={item.path}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          baseClasses,
          isActive
            ? 'bg-bg-subtle text-fg'
            : 'text-fg-muted hover:bg-bg-subtle hover:text-fg'
        )
      }
    >
      <Icon className="w-4 h-4 shrink-0" strokeWidth={1.75} />
      <span className="truncate">{item.label}</span>
      <ItemBadge item={item} />
    </NavLink>
  )
}

interface SidebarProps {
  mobileOpen: boolean
  onMobileClose: () => void
}

export function Sidebar({ mobileOpen, onMobileClose }: SidebarProps) {
  return (
    <>
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="lg:hidden fixed inset-0 z-40 bg-fg/30 backdrop-blur-sm animate-fade-in"
          onClick={onMobileClose}
          aria-hidden
        />
      )}

      <aside
        className={cn(
          'fixed lg:sticky top-0 left-0 z-50 lg:z-auto',
          'h-screen w-[240px] shrink-0',
          'bg-bg border-r border-border-subtle',
          'flex flex-col',
          'transition-transform duration-200 ease-out',
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        )}
      >
        {/* Logo */}
        <div className="h-14 flex items-center justify-between px-4 border-b border-border-subtle shrink-0">
          <Link to="/dashboard" onClick={onMobileClose}>
            <Logo />
          </Link>
          <button
            type="button"
            onClick={onMobileClose}
            className="lg:hidden p-1.5 -mr-1.5 rounded-md text-fg-muted hover:bg-bg-subtle"
            aria-label="Закрыть меню"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Scrollable nav */}
        <nav className="flex-1 overflow-y-auto py-3 px-2">
          <ul className="flex flex-col gap-0.5">
            {NAV_GROUPS.map((group, gi) => (
              <li key={gi} className="flex flex-col gap-0.5">
                {group.header && (
                  group.headerPath ? (
                    <NavLink
                      to={group.headerPath}
                      onClick={onMobileClose}
                      end
                      className={({ isActive }) =>
                        cn(
                          'px-2.5 pt-4 pb-1.5 text-[10px] font-semibold uppercase tracking-wider transition-colors',
                          isActive ? 'text-fg' : 'text-fg-subtle hover:text-fg'
                        )
                      }
                    >
                      {group.header}
                    </NavLink>
                  ) : (
                    <div className="px-2.5 pt-4 pb-1.5 text-[10px] font-semibold text-fg-subtle uppercase tracking-wider">
                      {group.header}
                    </div>
                  )
                )}
                {group.items.map((item) => (
                  <SidebarItem key={item.path} item={item} onNavigate={onMobileClose} />
                ))}
              </li>
            ))}
          </ul>
        </nav>

        {/* Footer items */}
        <div className="border-t border-border-subtle px-2 py-3 shrink-0">
          <ul className="flex flex-col gap-0.5">
            {FOOTER_NAV.map((item) => (
              <li key={item.path}>
                <SidebarItem item={item} onNavigate={onMobileClose} />
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </>
  )
}
