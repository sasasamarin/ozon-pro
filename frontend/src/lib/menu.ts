import type { LucideIcon } from 'lucide-react'
import {
  LayoutDashboard,
  BarChart3,
  Target,
  Filter,
  FlagTriangleRight,
  Grid3x3,
  AlertTriangle,
  Calendar,
  Package,
  Calculator,
  Tags,
  Eye,
  FolderTree,
  ShoppingBag,
  Truck,
  PackageCheck,
  RotateCcw,
  Ban,
  TrendingUp,
  Activity,
  Receipt,
  Wallet,
  Landmark,
  Percent,
  Users,
  FileText,
  Sparkles,
  Shield,
  CreditCard,
  Repeat,
  Bell,
  Settings as SettingsIcon,
  History,
  Send,
  MessageSquare,
  Store,
  Plug,
  HelpCircle,
} from 'lucide-react'

export type NavBadge = 'killer' | 'premium' | 'ai'

export interface PlaceholderContent {
  description: string
  plannedFeatures: string[]
}

export interface NavItem {
  path: string
  label: string
  icon: LucideIcon
  badge?: NavBadge
  /** If present, this route renders <PagePlaceholder>. Routes without it are wired to real pages. */
  placeholder?: PlaceholderContent
  /** If present, the sidebar renders this as an external <a target="_blank"> instead of an in-app route. */
  externalUrl?: string
}

export interface NavGroup {
  /** undefined for ungrouped (single item at top) */
  header?: string
  /** Если заполнено — заголовок секции кликабельный и ведёт по этому пути.
   *  Используется когда у секции есть "корневая" страница, на которой собрано
   *  всё содержимое раздела (например /orders), а sub-pages — фильтры/срезы.
   */
  headerPath?: string
  items: NavItem[]
}

// === MAIN SIDEBAR ===

export const NAV_GROUPS: NavGroup[] = [
  {
    items: [
      { path: '/dashboard', label: 'Дашборд', icon: LayoutDashboard },
    ],
  },
  {
    header: 'Аналитика',
    items: [
      {
        path: '/analytics/summary',
        label: 'Сводка по магазинам',
        icon: BarChart3,
        placeholder: {
          description: 'Все ключевые метрики магазинов на одном экране.',
          plannedFeatures: [
            'Общая выручка, маржа, заказы по всем кабинетам',
            'Сравнение магазинов в одной таблице',
            'Динамика 7 / 30 / 90 дней с цветовой разметкой',
            'Топ-10 SKU по выручке и по марже',
            'Быстрые drill-downs: клик по магазину → детали',
          ],
        },
      },
      {
        path: '/analytics/reverse-funnel',
        label: 'Обратная воронка',
        icon: Target,
        badge: 'killer',
        placeholder: {
          description:
            'Главная фишка Flowoi. Задай цель — AI рассчитает что нужно делать, чтобы её достичь.',
          plannedFeatures: [
            'Ввод цели: выручка / прибыль / заказы / маржа + период',
            'AI-расчёт сценариев: реклама, оптимизация карточки, цена',
            'Интерактивные слайдеры бюджета и цены — реалтайм-прогноз',
            'Сравнение нескольких сценариев side-by-side',
            'Progress tracking к цели с еженедельными чек-поинтами',
          ],
        },
      },
      {
        path: '/analytics/funnel',
        label: 'Обычная воронка',
        icon: Filter,
        placeholder: {
          description: 'Воронка от показа карточки до выкупа. Где теряются клиенты.',
          plannedFeatures: [
            'Показы → клики → корзина → заказ → выкуп',
            'Конверсия на каждом шаге с эталоном по категории',
            'Сравнение по периодам и магазинам',
            'Автодетект аномалий: где провалилась конверсия',
            'Drill-down по SKU на каждом шаге воронки',
          ],
        },
      },
      {
        path: '/sales-plan',
        label: 'План продаж',
        icon: FlagTriangleRight,
        placeholder: {
          description: 'Bottom-up план продаж + факт + KPI + игровой режим.',
          plannedFeatures: [
            'Задать план по выручке / прибыли / заказам / марже',
            'Цвет-кодированные отставания и опережения',
            'Прогноз на конец периода исходя из текущей динамики',
            'Сравнение с прошлым месяцем / годом',
            'Декомпозиция отставания: куда уходит "недополученная" выручка',
          ],
        },
      },
      {
        path: '/analytics/metrics-matrix',
        label: 'Матрица метрик',
        icon: Grid3x3,
      },
      {
        path: '/analytics/builder',
        label: 'Конструктор графиков',
        icon: TrendingUp,
      },
      {
        path: '/analytics/heatmap',
        label: 'Карта товаров',
        icon: Grid3x3,
        placeholder: {
          description: 'Все SKU на одной карте: размер = выручка, цвет = маржинальность.',
          plannedFeatures: [
            'Treemap-визуализация всего ассортимента',
            'Фильтры по категории, магазину, цене, остатку',
            'Drill-down по клику на товар',
            'Группировка: по категории / по бренду / по складу',
            'Экспорт картинки и данных',
          ],
        },
      },
      {
        path: '/analytics/stockouts',
        label: 'Стокауты',
        icon: AlertTriangle,
        placeholder: {
          description: 'Когда и какой товар уйдёт в out-of-stock. Сколько денег теряем.',
          plannedFeatures: [
            'Прогноз остатка на 7 / 14 / 30 дней',
            'Расчёт потерянной выручки от out-of-stock',
            'Алерт за N дней до окончания товара',
            'История stockout-ов и их стоимости',
            'Привязка к "прогнозу закупок" — закрыть цикл',
          ],
        },
      },
      {
        path: '/analytics/storage-warning',
        label: 'Не попасть на хранение',
        icon: AlertTriangle,
      },
      {
        path: '/analytics/competitor',
        label: 'Конкуренты',
        icon: Target,
      },
      {
        path: '/analytics/seasonality',
        label: 'Сезонность',
        icon: Calendar,
        placeholder: {
          description: 'Сезонные пики и провалы по каждому товару.',
          plannedFeatures: [
            'Year-over-year графики продаж по SKU и категориям',
            'Автодетект сезонных товаров (пик/провал)',
            'Календарь сезонных событий: НГ, 11.11, школа, лето',
            'Рекомендации по закупкам под сезон',
            'Прогноз пика с учётом исторических данных',
          ],
        },
      },
    ],
  },
  {
    header: 'Товары',
    headerPath: '/products',
    items: [
      {
        path: '/products',
        label: 'Каталог',
        icon: Package,
        placeholder: {
          description: 'Все товары всех кабинетов в одном списке.',
          plannedFeatures: [
            'Фильтры и сортировка по любому полю',
            'Групповые операции: цены, теги, архив',
            'Принудительная синхронизация с Ozon',
            'Метки и ярлыки (свои + автоматические)',
            'Поиск по названию / артикулу / SKU',
          ],
        },
      },
      {
        path: '/products/economics',
        label: 'Экономика продаж',
        icon: TrendingUp,
      },
      {
        path: '/products/stats',
        label: 'Статистика товара',
        icon: Grid3x3,
      },
      {
        path: '/whatif',
        label: 'Симулятор «Что если»',
        icon: Calculator,
      },
      {
        path: '/products/calculator',
        label: 'Юнит-калькулятор',
        icon: Calculator,
        placeholder: {
          description: 'Считай юнит-экономику до того как закупать.',
          plannedFeatures: [
            'Ввод себестоимости + цены продажи',
            'Авто-расчёт комиссий Ozon, логистики, эквайринга, рекламы',
            'What-if по цене и СПП в реалтайме',
            'Минимальная цена для безубыточности',
            'Сохранение сценариев и сравнение между собой',
          ],
        },
      },
      {
        path: '/products/prices',
        label: 'Цены и маржа',
        icon: Tags,
        placeholder: {
          description: 'Управление ценами всех SKU.',
          plannedFeatures: [
            'Массовое изменение цен с превью результата',
            'Индекс цен Ozon: Profit / Avg / Non-Profit с подсветкой',
            'Минимальная цена для безубыточности на каждом SKU',
            'История изменений цен (audit log)',
            'Импорт/экспорт прайса CSV',
          ],
        },
      },
      {
        path: '/products/competitors',
        label: 'Конкуренты',
        icon: Eye,
        badge: 'premium',
        placeholder: {
          description: 'Кто продаёт похожие товары и за сколько. Только Premium Plus.',
          plannedFeatures: [
            'До 8 конкурентов на каждый SKU (Premium Plus API)',
            'Мониторинг их цен и доступности',
            'История движений цен и остатков',
            'Сравнение по выручке (если доступно)',
            'Алерт когда конкурент снизил цену ниже твоей',
          ],
        },
      },
      {
        path: '/products/categories',
        label: 'Категории',
        icon: FolderTree,
        placeholder: {
          description: 'Дерево категорий Ozon, твоя позиция и потенциал.',
          plannedFeatures: [
            'Иерархия категорий Ozon',
            'Размер рынка по категории (если доступно)',
            'Твоя доля и позиция',
            'Рекомендации по расширению ассортимента',
            'Сравнение маржинальности по категориям',
          ],
        },
      },
    ],
  },
  {
    header: 'Заказы',
    headerPath: '/orders',
    items: [
      {
        path: '/orders',
        label: 'Все заказы',
        icon: ShoppingBag,
        placeholder: {
          description: 'Все заказы по всем магазинам и складам.',
          plannedFeatures: [
            'Единый список FBO + FBS + RFBS',
            'Фильтры: статус, дата, город, кластер, магазин',
            'Drill-down по заказу: позиции, финансы, статус-история',
            'Экспорт в Excel / CSV',
            'Поиск по номеру отправления и покупателю',
          ],
        },
      },
      {
        path: '/orders/fbo',
        label: 'FBO заказы',
        icon: Truck,
        placeholder: {
          description: 'Заказы со склада Ozon.',
          plannedFeatures: [
            'Список FBO-отправлений со статусами',
            'Аналитика по кластерам отгрузки и доставки',
            'Скорость комплектации Ozon (по своему складу — N/A)',
            'Финансовая разбивка: комиссия + логистика + эквайринг',
            'Группировка по дням и неделям',
          ],
        },
      },
      {
        path: '/orders/fbs',
        label: 'FBS заказы',
        icon: PackageCheck,
        placeholder: {
          description: 'Заказы со своего склада.',
          plannedFeatures: [
            'Список FBS-отправлений с дедлайнами отгрузки',
            'Опоздания по SLA с цветовой разметкой',
            'Печать этикеток и сопроводительных документов',
            'Статус-история каждого заказа',
            'Сборка: что лежит ждать комплектации',
          ],
        },
      },
      {
        path: '/orders/returns',
        label: 'Возвраты',
        icon: RotateCcw,
        placeholder: {
          description: 'Возвраты и невыкупы. Главные причины и стоимость.',
          plannedFeatures: [
            'Список возвратов с причинами',
            'Группировка по товарам и категориям',
            'Стоимость обратной логистики (фактическая)',
            'Тренд возвратов 30 / 90 / 365 дней',
            'Топ-проблемных SKU с автоматическими рекомендациями',
          ],
        },
      },
      {
        path: '/orders/cancellations',
        label: 'Отмены',
        icon: Ban,
        placeholder: {
          description: 'Отменённые заказы. Кто и почему.',
          plannedFeatures: [
            'Отмены покупателем vs магазином',
            'Причины с группировкой',
            'Потерянная выручка от отмен',
            'Алерт если процент отмен у магазина растёт',
            'Профилактика: автоматические рекомендации',
          ],
        },
      },
    ],
  },
  {
    header: 'Финансы',
    items: [
      {
        path: '/finance/p-and-l',
        label: 'P&L отчёт',
        icon: TrendingUp,
        placeholder: {
          description: 'Прибыли и убытки по магазинам. Полный финансовый расклад.',
          plannedFeatures: [
            'Выручка минус возвраты, комиссии, логистика, эквайринг',
            'Расходы: себестоимость, реклама, аренда, кредиты, зарплаты, налоги',
            'Сравнение периодов: месяц / квартал / год',
            'Drill-down по каждой статье',
            'Экспорт в Excel со всеми разрезами',
          ],
        },
      },
      {
        path: '/finance/balance',
        label: 'Товарный баланс',
        icon: Wallet,
      },
      {
        path: '/finance/cashflow',
        label: 'Cashflow',
        icon: Activity,
        placeholder: {
          description: 'Денежный поток в реальном времени. Когда придут деньги, когда платить.',
          plannedFeatures: [
            'Входящие от Ozon по графику выплат',
            'Исходящие: закупки, кредиты, налоги, реклама, расходы',
            'Прогноз баланса на 30 / 60 / 90 дней',
            'Алерт при риске кассового разрыва',
            'What-if: что если задержать закупку / взять кредит',
          ],
        },
      },
      {
        path: '/finance/transactions',
        label: 'Транзакции Ozon',
        icon: Receipt,
        placeholder: {
          description: 'Каждая операция Ozon: продажа, комиссия, реклама, возврат.',
          plannedFeatures: [
            'Полный список транзакций с фильтрами',
            'Группировка по типу: продажа / комиссия / логистика / реклама',
            'Привязка к заказам (posting_number)',
            'Сравнение начислений с выписками банка',
            'Экспорт для бухгалтера',
          ],
        },
      },
      {
        path: '/finance/expenses',
        label: 'Внешние расходы',
        icon: Wallet,
        placeholder: {
          description: 'Аренда, зарплаты, логистика — расходы вне Ozon.',
          plannedFeatures: [
            'Добавление расходов вручную или импортом CSV',
            'Категории расходов: ФОТ / аренда / логистика / маркетинг',
            'Регулярные платежи (раз в месяц / квартал)',
            'Распределение расходов между магазинами',
            'Влияние на P&L и cashflow',
          ],
        },
      },
      {
        path: '/finance/taxes',
        label: 'Налоги',
        icon: Landmark,
        placeholder: {
          description: 'Налоговая база и платежи. УСН и НДС.',
          plannedFeatures: [
            'Налоговая база по магазинам и периодам',
            'Расчёт УСН 6% / 15% и НДС',
            'Отчётные периоды и дедлайны',
            'Экспорт для бухгалтера или 1С',
            'Прогноз налогов на конец квартала',
          ],
        },
      },
      {
        path: '/finance/margin',
        label: 'Маржинальность',
        icon: Percent,
        placeholder: {
          description: 'Маржа по каждому SKU и магазину с учётом всех расходов.',
          plannedFeatures: [
            'Маржа на единицу и в процентах',
            'ROI по товарам',
            'Топ низкомаржинальных и убыточных SKU',
            'What-if по цене и себестоимости',
            'Сравнение маржи между магазинами',
          ],
        },
      },
    ],
  },
  {
    header: 'Закупки',
    items: [
      {
        path: '/procurement/supplies',
        label: 'Поставки',
        icon: Truck,
      },
      {
        path: '/procurement/suppliers',
        label: 'Поставщики',
        icon: Users,
        placeholder: {
          description: 'Все поставщики, контакты, условия.',
          plannedFeatures: [
            'Карточки поставщиков с контактами и реквизитами',
            'История закупок у каждого поставщика',
            'Рейтинг по качеству, цене, срокам',
            'Документы: договоры, счета',
            'Сравнение цен между поставщиками на один SKU',
          ],
        },
      },
      {
        path: '/procurement/orders',
        label: 'Заказы поставщикам',
        icon: FileText,
        placeholder: {
          description: 'Текущие и архивные заказы у поставщиков.',
          plannedFeatures: [
            'Список заказов со статусами: заказан / в пути / получен',
            'Документы по заказу',
            'Расчёт с поставщиком (что оплачено, что висит)',
            'Привязка к "ожидаемым поступлениям" в cashflow',
            'Шаблон заказа для повторных закупок',
          ],
        },
      },
      {
        path: '/procurement/forecast',
        label: 'Прогноз закупок',
        icon: Sparkles,
        badge: 'ai',
        placeholder: {
          description: 'AI смотрит на продажи и сезонность, говорит что и когда закупать.',
          plannedFeatures: [
            'Прогноз спроса на 30 / 60 / 90 дней по каждому SKU',
            'Рекомендуемый размер закупки',
            'Оптимальный момент заказа (с учётом lead time)',
            'Риск-метки: overstock / stockout',
            'Сценарии: консервативный / агрессивный / по бюджету',
          ],
        },
      },
      {
        path: '/procurement/calendar',
        label: 'Календарь поставок',
        icon: Calendar,
        placeholder: {
          description: 'Когда товар придёт на склад и какие риски.',
          plannedFeatures: [
            'Timeline всех ожидаемых поставок',
            'Дедлайны отгрузки на Ozon',
            'Цветовая разметка задержек и опозданий',
            'Уведомления накануне поставки',
            'Связка с прогнозом: чтобы товар не закончился до прихода',
          ],
        },
      },
      {
        path: '/procurement/quality',
        label: 'Контроль качества',
        icon: Shield,
        placeholder: {
          description: 'Брак и возвраты к поставщикам.',
          plannedFeatures: [
            'Список инцидентов с фото и документами',
            'Возврат поставщику с финансовым закрытием',
            'Статистика брака по поставщикам',
            'Связка с возвратами от покупателей',
            'Чек-листы приёмки',
          ],
        },
      },
    ],
  },
  {
    header: 'Кредиты',
    items: [
      {
        path: '/loans',
        label: 'Кредиты (вручную)',
        icon: CreditCard,
      },
      {
        path: '/credit',
        label: 'Услуги ускоренного вывода Ozon',
        icon: Landmark,
      },
      {
        path: '/credits/schedule',
        label: 'График платежей',
        icon: Calendar,
        placeholder: {
          description: 'Когда и сколько платить по каждому кредиту.',
          plannedFeatures: [
            'Календарь платежей всех кредитов на одной шкале',
            'Общий объём платежей в месяц',
            'Напоминания за N дней до даты',
            'Возможность изменить график (если банк согласен)',
            'Экспорт для финансового планирования',
          ],
        },
      },
      {
        path: '/credits/cashflow-impact',
        label: 'Влияние на cashflow',
        icon: Activity,
        placeholder: {
          description: 'Как платежи по кредитам бьют по кассе.',
          plannedFeatures: [
            'Наложение кредитного графика на cashflow-прогноз',
            'Подсветка месяцев с риском кассового разрыва',
            'What-if без одного из кредитов',
            'Рекомендация когда брать новый кредит безопасно',
            'Расчёт долговой нагрузки (debt-to-revenue)',
          ],
        },
      },
      {
        path: '/credits/refinance',
        label: 'Рефинансирование',
        icon: Repeat,
        placeholder: {
          description: 'Сценарии замены текущих кредитов на более выгодные.',
          plannedFeatures: [
            'Ввод новых предложений банков (ставка, срок)',
            'Сравнение экономии за весь срок',
            'Новый график платежей',
            'Учёт штрафов за досрочное погашение',
            'Рекомендация рефинансировать / оставить',
          ],
        },
      },
    ],
  },
  {
    header: 'Маркеры и алерты',
    items: [
      {
        path: '/alerts',
        label: 'Активные алерты',
        icon: Bell,
        placeholder: {
          description: 'Что требует внимания прямо сейчас.',
          plannedFeatures: [
            'Список открытых алертов с приоритетом',
            'Фильтры: магазин, тип, приоритет',
            '"Отметить как просмотренное" / "В работу"',
            'Группировка по типу события',
            'Связка с задачами и пометками',
          ],
        },
      },
      {
        path: '/alerts/settings',
        label: 'Настройки маркеров',
        icon: SettingsIcon,
        placeholder: {
          description: 'Какие события и пороги должны срабатывать.',
          plannedFeatures: [
            'Правила: stockout < N дней, маржа < X%, отзыв ниже Y',
            'Персонализация порогов под каждый магазин',
            'Шаблоны: "консервативный" / "агрессивный"',
            'Включить / выключить отдельные категории алертов',
            'Тестирование правила на исторических данных',
          ],
        },
      },
      {
        path: '/alerts/history',
        label: 'История',
        icon: History,
        placeholder: {
          description: 'Все срабатывания за период. Что было — что сделали.',
          plannedFeatures: [
            'Журнал срабатываний алертов',
            'Действие пользователя: проигнорировано / в работу / закрыто',
            'Статистика по причинам и магазинам',
            'Экспорт для retrospective-разборов',
            'Поиск по тексту алерта',
          ],
        },
      },
      {
        path: '/alerts/channels',
        label: 'Каналы доставки',
        icon: Send,
        placeholder: {
          description: 'Куда слать: Telegram, email, push, webhook.',
          plannedFeatures: [
            'Подключение каналов: Telegram, email, webhook',
            'Расписание "тихих часов" по дням недели',
            'Тестовая отправка',
            'Разные правила маршрутизации на разные типы алертов',
            'Эскалация: если не прочитано N часов — другой канал',
          ],
        },
      },
    ],
  },
  {
    items: [
      {
        path: '/ai/chat',
        label: 'AI-чат',
        icon: MessageSquare,
        badge: 'ai',
      },
      {
        path: '/telegram',
        label: 'Telegram бот',
        icon: Send,
        placeholder: {
          description: 'Бот Flowoi в Telegram: алерты, быстрые отчёты, чат.',
          plannedFeatures: [
            'Подключение бота к аккаунту через one-time code',
            'Ежедневная сводка в заданное время',
            'Команды: /revenue /stockouts /pl /margin',
            'Чат-интерфейс с тем же AI, что и в веб-приложении',
            'Push-алерты в Telegram при критичных событиях',
          ],
        },
      },
    ],
  },
]

// === FOOTER (нижняя секция сайдбара) ===

export const FOOTER_NAV: NavItem[] = [
  { path: '/cabinets', label: 'Кабинеты', icon: Store },
  {
    path: '/team',
    label: 'Команда и роли',
    icon: Users,
    placeholder: {
      description: 'Пригласи команду в Flowoi и раздай права.',
      plannedFeatures: [
        'Список пользователей и их роли',
        'Роли: Owner / Admin / Analyst / Viewer',
        'Приглашение по email с одноразовой ссылкой',
        'Аудит действий: кто что менял и когда',
        'Гранулярные права на конкретный магазин',
      ],
    },
  },
  {
    path: '/integrations',
    label: 'Интеграции',
    icon: Plug,
    placeholder: {
      description: 'Интеграции с банками, 1С, маркетплейсами кроме Ozon.',
      plannedFeatures: [
        '1С: выгрузка проводок и приёмки',
        'Банк-выписки (Тинькофф / Сбер) для cashflow',
        'Wildberries (на roadmap)',
        'Экспорт в Google Sheets',
        'Webhook для собственных интеграций',
      ],
    },
  },
  { path: '/settings', label: 'Настройки', icon: SettingsIcon },
  {
    path: '/support',
    label: 'Поддержка',
    icon: HelpCircle,
    externalUrl: 'https://t.me/codexa_support',
  },
]

/** Flat list of all items that should be wired as placeholder routes. */
export function getAllPlaceholderItems(): NavItem[] {
  const fromGroups = NAV_GROUPS.flatMap((g) => g.items).filter((i) => i.placeholder)
  const fromFooter = FOOTER_NAV.filter((i) => i.placeholder)
  return [...fromGroups, ...fromFooter]
}
