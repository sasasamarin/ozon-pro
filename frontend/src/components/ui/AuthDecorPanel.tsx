import { TrendingUp, CheckCircle2, Package } from 'lucide-react'
import { Sparkline } from './Sparkline'
import { Logo } from './Logo'

export function AuthDecorPanel() {
  return (
    <aside className="relative hidden lg:block overflow-hidden bg-aurora">
      {/* Grid overlay */}
      <div className="absolute inset-0 bg-grid-faint opacity-70 pointer-events-none" />
      {/* Vignette to soften edges */}
      <div className="absolute inset-0 bg-gradient-to-tr from-white/30 via-transparent to-white/10 pointer-events-none" />

      {/* Floating cards */}
      <div className="relative h-full flex flex-col justify-between p-12 xl:p-16">
        {/* Top floating revenue card */}
        <div className="flex justify-end">
          <div className="w-[280px] rounded-xl bg-white/70 backdrop-blur-xl border border-white/60 shadow-glass p-5 animate-slide-up">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-50 to-rose-50 border border-white flex items-center justify-center">
                  <TrendingUp className="w-4 h-4 text-fg-muted" />
                </div>
                <div>
                  <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">Оборот · 30 дней</p>
                </div>
              </div>
              <span className="text-[11px] font-semibold text-success bg-green-50/80 px-2 py-0.5 rounded-full tabular-nums">
                +18.4%
              </span>
            </div>
            <p className="text-2xl font-semibold text-fg tabular-nums mt-2">12 482 000 ₽</p>
            <div className="text-success mt-2 -mx-1">
              <Sparkline points={[34, 38, 36, 42, 45, 41, 50, 54, 51, 58, 62, 60, 68, 72, 75]} />
            </div>
          </div>
        </div>

        {/* Middle floating activity */}
        <div className="flex justify-start -mt-8 lg:-mt-12 xl:-mt-16">
          <div className="w-[300px] rounded-xl bg-white/65 backdrop-blur-xl border border-white/60 shadow-glass p-4 animate-slide-up [animation-delay:80ms]">
            <p className="text-[11px] font-medium text-fg-muted uppercase tracking-wider mb-3">Последние действия</p>
            <ul className="space-y-2.5">
              <li className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2 text-fg">
                  <span className="w-1.5 h-1.5 rounded-full bg-success" />
                  STOLZ KRAFT — синхронизация
                </span>
                <span className="text-xs font-mono text-fg-subtle">12с</span>
              </li>
              <li className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2 text-fg">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
                  Аналитика · отчёт готов
                </span>
                <span className="text-xs font-mono text-fg-subtle">3м</span>
              </li>
              <li className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2 text-fg-muted">
                  <span className="w-1.5 h-1.5 rounded-full bg-fg-subtle" />
                  Импорт остатков
                </span>
                <span className="text-xs font-mono text-fg-subtle">1ч</span>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom-right floating chip + tagline */}
        <div className="flex flex-col gap-6">
          <div className="self-end inline-flex items-center gap-2 rounded-full bg-white/70 backdrop-blur-xl border border-white/60 shadow-glass px-3 py-1.5 animate-slide-up [animation-delay:160ms]">
            <CheckCircle2 className="w-3.5 h-3.5 text-success" />
            <span className="text-xs font-medium text-fg">Синхронизировано 24 кабинета</span>
          </div>

          <div className="inline-flex items-center gap-2 rounded-full bg-white/70 backdrop-blur-xl border border-white/60 shadow-glass px-3 py-1.5 self-start animate-slide-up [animation-delay:200ms]">
            <Package className="w-3.5 h-3.5 text-fg-muted" />
            <span className="text-xs font-medium text-fg tabular-nums">128 374 SKU в работе</span>
          </div>

          <div className="max-w-md">
            <Logo className="h-12 mb-5" />
            <h2 className="text-3xl font-semibold text-fg tracking-tight text-balance">
              Финансовый мозг для&nbsp;селлеров Ozon
            </h2>
            <p className="text-sm text-fg-muted mt-2 max-w-sm">
              Юнит-экономика, остатки, реклама и прибыль — в одном кабинете. Без таблиц и догадок.
            </p>
          </div>
        </div>
      </div>
    </aside>
  )
}
