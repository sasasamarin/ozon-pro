import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'
import { ErrorBoundary } from './ErrorBoundary'
import { AIDrawer } from './AIDrawer'

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()

  return (
    <div className="min-h-screen bg-bg lg:grid lg:grid-cols-[240px_1fr]">
      <Sidebar mobileOpen={mobileOpen} onMobileClose={() => setMobileOpen(false)} />

      <div className="flex flex-col min-h-screen min-w-0">
        <Topbar onOpenSidebar={() => setMobileOpen(true)} />

        <main className="flex-1 px-4 sm:px-6 py-8 animate-fade-in">
          <div className="max-w-7xl mx-auto">
            <ErrorBoundary key={location.pathname} name={location.pathname}>
              <Outlet />
            </ErrorBoundary>
          </div>
        </main>
      </div>

      {/* AI Drawer — slide-out справа. Любая страница, любая кнопка
          AskAIButton открывает его не уходя со страницы. */}
      <AIDrawer />
    </div>
  )
}
