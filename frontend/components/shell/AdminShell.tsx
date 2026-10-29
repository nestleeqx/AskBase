"use client";

import {
  ArrowUpRight,
  CalendarCheck,
  ChartColumn,
  CircleHelp,
  FileStack,
  Globe,
  Inbox,
  Menu,
  MessagesSquare,
  SearchCheck,
  Settings2,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { CLINIC_RULES_PATH } from "@/lib/site";
import { SoundToggle, useAlerts } from "./Alerts";
import { Logo } from "../Logo";

type Item = {
  href: string;
  label: string;
  icon: ReactNode;
  /** Число в меню; null — ещё грузится (на проде первый запрос бывает долгим) */
  badge?: number | null;
  external?: boolean;
};

const NAV_ITEM = "group flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm transition-colors";

function NavItem({ item, onNavigate }: { item: Item; onNavigate?: () => void }) {
  const pathname = usePathname();
  const active = !item.external && pathname === item.href;
  const className = `${NAV_ITEM} ${
    active ? "bg-sunken font-medium text-ink" : "text-ink-2 hover:bg-sunken/70 hover:text-ink"
  }`;

  // Сайт клиники — статичная HTML-страница, а не страница приложения: обычная ссылка без
  // предзагрузки Next.js (иначе он запрашивает её как маршрут и получает 404 в консоли)
  if (item.external)
    return (
      <a href={item.href} target="_blank" rel="noreferrer" onClick={onNavigate} className={className}>
        <span className="text-ink-3 group-hover:text-ink-2">{item.icon}</span>
        {item.label}
        <ArrowUpRight className="ml-auto size-3.5 text-ink-3" />
      </a>
    );

  return (
    <Link href={item.href} onClick={onNavigate} aria-current={active ? "page" : undefined} className={className}>
      <span className={active ? "text-accent" : "text-ink-3 group-hover:text-ink-2"}>{item.icon}</span>
      {item.label}

      {item.badge === null && <span className="skeleton ml-auto h-4 w-5 rounded-md" aria-hidden />}
      {!!item.badge && (
        <span
          className={`ml-auto min-w-5 rounded-md px-1.5 py-px text-center text-[11px] font-semibold tabular-nums ${
            active ? "bg-accent text-white" : "bg-sunken text-ink-2"
          }`}
        >
          {item.badge}
        </span>
      )}
    </Link>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  // Тот же запрос, что у страницы документов, — SWR его не дублирует
  const { data } = useSWR("documents", () => api.documents());
  const knowledge: Item[] = [
    {
      href: "/admin/documents",
      label: "Документы",
      icon: <FileStack className="size-4" />,
      badge: data ? data.total : null,
    },
    { href: "/admin/search", label: "Проверка поиска", icon: <SearchCheck className="size-4" /> },
  ];
  // Бейджи: сколько клиентов ждут администратора и сколько заявок ждут звонка
  const { data: dialogs } = useSWR(["dialogs", "", false], () => api.dialogs(), { refreshInterval: 10000 });
  const { data: bookings } = useSWR("bookings", () => api.bookings(), { refreshInterval: 10000 });
  const { data: auth } = useSWR("auth", api.auth);
  // Тот же ключ, что у вкладки «Нерешённые», — после ответа в базу бейдж обновится сам
  const { data: unanswered } = useSWR(["unanswered", "open"], () => api.unanswered("open"), {
    refreshInterval: 10000,
  });
  const bot: Item[] = [
    {
      href: "/admin/dialogs",
      label: "Диалоги",
      icon: <Inbox className="size-4" />,
      badge: dialogs ? dialogs.waiting : null,
    },
    {
      href: "/admin/bookings",
      label: "Заявки на запись",
      icon: <CalendarCheck className="size-4" />,
      badge: bookings ? bookings.new : null,
    },
    { href: "/admin/chat", label: "Тестовый чат", icon: <MessagesSquare className="size-4" /> },
  ];
  const insights: Item[] = [
    {
      href: "/admin/unanswered",
      label: "Бот не смог ответить",
      icon: <CircleHelp className="size-4" />,
      badge: unanswered ? unanswered.open : null,
    },
    { href: "/admin/analytics", label: "Аналитика", icon: <ChartColumn className="size-4" /> },
  ];
  const clinic: Item[] = [
    { href: "/admin/settings", label: "Настройки бота", icon: <Settings2 className="size-4" /> },
    { href: CLINIC_RULES_PATH, label: "Сайт клиники", icon: <Globe className="size-4" />, external: true },
  ];

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center px-5">
        <Link href="/admin/dialogs" aria-label="AskBase — к диалогам" onClick={onNavigate}>
          <Logo />
        </Link>
      </div>
      <nav className="flex-1 space-y-6 overflow-y-auto px-3 pt-2 scrollbar-thin">
        <div>
          <p className="mb-1.5 px-2.5 text-[11px] font-medium text-ink-3">Бот</p>
          <div className="space-y-0.5">
            {bot.map((item) => (
              <NavItem key={item.href} item={item} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
        <div>
          <p className="mb-1.5 px-2.5 text-[11px] font-medium text-ink-3">База знаний</p>
          <div className="space-y-0.5">
            {knowledge.map((item) => (
              <NavItem key={item.href} item={item} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
        <div>
          <p className="mb-1.5 px-2.5 text-[11px] font-medium text-ink-3">Качество ответов</p>
          <div className="space-y-0.5">
            {insights.map((item) => (
              <NavItem key={item.href} item={item} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
        <div>
          <p className="mb-1.5 px-2.5 text-[11px] font-medium text-ink-3">Клиника</p>
          <div className="space-y-0.5">
            {clinic.map((item) => (
              <NavItem key={item.href} item={item} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
      </nav>
      <div className="p-3">
        <div className="rounded-2xl border border-line bg-canvas p-3.5">
          <p className="text-[13px] font-semibold text-ink">
            {auth?.owner ? "Вы — владелец клиники" : "Демо: клиника «Белая линия»"}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-ink-2">
            {auth?.owner
              ? "Документы и настройки бота, которые вы меняете, действуют для всех клиентов."
              : "Документы клиники общие для всех. Свои документы видите только вы — через сутки они удаляются."}
          </p>
        </div>
      </div>
    </div>
  );
}

/** Кто вошёл: гость демо или владелец клиники. Клик — на страницу входа: там и выход
 *  из режима владельца («Войти как гость» сбрасывает его вход), поэтому отдельной кнопки нет. */
function ClinicBadge() {
  const { data: auth } = useSWR("auth", api.auth);
  const owner = !!auth?.owner;
  return (
    <span className="flex items-center gap-2">
      <Link
        href="/login"
        className="flex items-center gap-2.5 rounded-xl py-1 pr-2 pl-1 transition-colors hover:bg-sunken"
        title={owner ? "Вы вошли как владелец клиники. Выйти или сменить вход" : "Гостевой доступ. Войти как владелец"}
      >
        <span className="grid size-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-[#5eead4] to-[#0d9488] text-sm font-semibold text-white">
          Б
        </span>
        <span className="leading-tight max-xl:hidden">
          <span className="block text-[13px] font-medium whitespace-nowrap text-ink">Клиника «Белая линия»</span>
          <span className="block text-[11px] text-ink-3">{owner ? "владелец" : "гостевой доступ"}</span>
        </span>
      </Link>
    </span>
  );
}

export function AdminShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  useAlerts();

  useEffect(() => {
    if (!menuOpen) return;
    const root = document.documentElement;
    const overflow = root.style.overflow;
    root.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => {
      root.style.overflow = overflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  return (
    <div className="min-h-full lg:pl-64">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-line bg-surface lg:block">
        <Sidebar />
      </aside>

      {/* На телефоне и планшете меню выезжает справа по кнопке */}
      {menuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="fade-in absolute inset-0 bg-ink/30" onClick={() => setMenuOpen(false)} />
          <aside
            className="slide-from-right absolute inset-y-0 right-0 w-72 max-w-[85vw] bg-surface shadow-xl"
            aria-label="Меню"
          >
            <button
              type="button"
              onClick={() => setMenuOpen(false)}
              aria-label="Закрыть меню"
              className="absolute top-3.5 right-3 grid size-9 place-items-center rounded-lg text-ink-2 hover:bg-sunken"
            >
              <X className="size-4.5" />
            </button>
            <Sidebar onNavigate={() => setMenuOpen(false)} />
          </aside>
        </div>
      )}

      <header className="sticky top-0 z-20 border-b border-line bg-canvas/85 backdrop-blur">
        <div className="flex h-16 items-center gap-3 px-4 sm:px-6">
          <Link href="/admin/dialogs" aria-label="AskBase — к диалогам" className="lg:hidden">
            <Logo />
          </Link>
          <div className="ml-auto flex items-center gap-2.5">
            <SoundToggle />
            <ClinicBadge />
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-label="Открыть меню"
              className="grid size-10 shrink-0 place-items-center rounded-xl border border-line bg-surface text-ink-2 lg:hidden"
            >
              <Menu className="size-4.5" />
            </button>
          </div>
        </div>
      </header>

      <main>{children}</main>
    </div>
  );
}
