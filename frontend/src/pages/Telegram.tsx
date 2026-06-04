/**
 * /telegram — настройки TG бота.
 * Сейчас — UI-заглушка с инструкцией. Полное подключение — после деплоя бота.
 */
import { Send, MessageCircle, Clock, Bell, AlertCircle } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'

export function Telegram() {
  return (
    <div className="space-y-5 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold text-fg flex items-center gap-2">
          <Send className="w-6 h-6 text-blue-500" />
          Telegram бот
        </h1>
        <p className="text-sm text-fg-muted mt-1">
          Алерты и быстрые отчёты прямо в чате. Подключение — через one-time код.
        </p>
      </div>

      <Card className="p-4 bg-amber-50/30 border-amber-200 flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
        <div className="text-sm">
          <b>Бот в работе.</b> Сейчас подключение недоступно — заканчиваем серверную часть.
          Подпишитесь на обновления в <a href="https://t.me/codexa_support" target="_blank" rel="noopener"
              className="text-blue-600 hover:underline">@codexa_support</a>, когда выкатим — пришлём.
        </div>
      </Card>

      <Card className="p-5 space-y-4">
        <h3 className="text-sm font-semibold text-fg">Что будет в боте</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Feature icon={Bell} label="Push-алерты"
            desc="Critical-алерты прилетают сразу. Warning — в дайджесте утром." />
          <Feature icon={Clock} label="Ежедневная сводка"
            desc="В 9:00 — выручка, заказы, остатки, что требует внимания." />
          <Feature icon={MessageCircle} label="Команды"
            desc="/revenue — за сегодня. /stockouts — что кончается. /pl — мини-P&L." />
          <Feature icon={Send} label="AI-чат"
            desc="Тот же AI что в /ai/chat, но через TG. Контекст по магазинам." />
        </div>
      </Card>

      <Card className="p-5">
        <h3 className="text-sm font-semibold text-fg mb-3">Как подключим (план)</h3>
        <ol className="list-decimal pl-5 space-y-2 text-sm text-fg-muted">
          <li>Откройте бот <code className="text-fg bg-bg-subtle px-1 rounded">@flowoi_bot</code> в Telegram</li>
          <li>Нажмите Start</li>
          <li>Вернитесь сюда — появится поле «Одноразовый код»</li>
          <li>Скопируйте код, отправьте боту командой <code className="text-fg bg-bg-subtle px-1 rounded">/link &lt;код&gt;</code></li>
          <li>Готово — все алерты с включённым каналом «telegram» поедут вам</li>
        </ol>
      </Card>

      <Card className="p-4 flex items-center justify-between gap-3">
        <div className="text-sm">
          <div className="font-semibold text-fg">Готов получить уведомление о запуске?</div>
          <div className="text-xs text-fg-muted mt-1">Напишите нам — закинем в early-access.</div>
        </div>
        <Button onClick={() => window.open('https://t.me/codexa_support', '_blank')}>
          Написать в поддержку
        </Button>
      </Card>
    </div>
  )
}

function Feature({ icon: Icon, label, desc }: { icon: any; label: string; desc: string }) {
  return (
    <div className="p-3 border border-border-subtle rounded">
      <div className="flex items-center gap-2 font-medium text-fg text-sm mb-1">
        <Icon className="w-4 h-4 text-blue-500" />
        {label}
      </div>
      <div className="text-xs text-fg-muted">{desc}</div>
    </div>
  )
}
