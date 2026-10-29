"use client";

import { ArrowUpRight, Info } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { formatSeconds, plural } from "@/lib/format";
import type { Analytics, AnalyticsDay } from "@/lib/types";
import { Panel } from "../ui";

const weekday = new Intl.DateTimeFormat("ru-RU", { weekday: "short" });
const dayMonth = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" });

// Дата «2026-10-28» — день в часовом поясе клиники; полдень, чтобы смещение браузера её не сдвинуло
function asDate(iso: string) {
  return new Date(`${iso}T12:00:00`);
}

function Stat({ label, value, hint, href }: { label: string; value: ReactNode; hint?: ReactNode; href?: string }) {
  const body = (
    <>
      {/* Справа у карточки-ссылки стрелка — текст до неё не доходит */}
      <p className={`text-xs text-ink-2 ${href ? "pr-5" : ""}`}>{label}</p>
      <p className="mt-1.5 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-xs leading-snug text-ink-3">{hint}</p>}
    </>
  );
  const cls = "rounded-2xl border border-line bg-surface p-4";
  return href ? (
    <Link href={href} className={`${cls} group relative transition-colors hover:border-accent/40`}>
      <ArrowUpRight className="absolute top-3.5 right-3.5 size-3.5 text-ink-3 group-hover:text-accent" />
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

// Прямые отрезки между точками: на семи днях сглаживание рисует волны, которых в данных нет
function polyline(points: [number, number][]) {
  return points.map(([x, y], i) => `${i ? "L" : "M"}${x},${y}`).join(" ");
}

function DaysChart({ days }: { days: AnalyticsDay[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...days.map((d) => d.dialogs));
  // Чистые деления оси: 0, половина, максимум, округлённый вверх
  const top = max <= 4 ? max : Math.ceil(max / 2) * 2;
  const ticks = [top, top / 2, 0];
  // Координаты в долях 0..100: x — середина дня, y — сверху вниз
  const pts: [number, number][] = days.map((d, i) => [((i + 0.5) / days.length) * 100, 100 - (d.dialogs / top) * 100]);
  const line = polyline(pts);
  const area = `${line} L${pts[pts.length - 1][0]},100 L${pts[0][0]},100 Z`;
  const peak = days.findIndex((d) => d.dialogs === max);

  return (
    <div>
      <div className="relative h-48 pl-7">
        {ticks.map((t) => (
          <div
            key={t}
            className={`absolute right-0 left-7 border-t ${t ? "border-dashed border-line" : "border-line-strong"}`}
            style={{ bottom: `${(t / top) * 100}%` }}
          >
            <span className="absolute -top-2 -left-7 w-5 text-right text-[11px] text-ink-3 tabular-nums">
              {Number.isInteger(t) ? t : ""}
            </span>
          </div>
        ))}
        <div className="absolute inset-0 left-7" onMouseLeave={() => setHover(null)}>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 size-full overflow-visible">
            <defs>
              <linearGradient id="days-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.22" />
                <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0" />
              </linearGradient>
            </defs>
            <path d={area} fill="url(#days-fill)" />
            <path
              d={line}
              fill="none"
              stroke="var(--color-accent)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
          {hover !== null && (
            <div
              className="absolute top-0 bottom-0 border-l border-dashed border-accent/50"
              style={{ left: `${pts[hover][0]}%` }}
            />
          )}
          {pts.map(([x, y], i) => (
            <span
              key={days[i].date}
              className={`absolute -translate-x-1/2 translate-y-1/2 rounded-full border-2 border-accent transition-all ${
                hover === i ? "size-3.5 bg-accent ring-4 ring-accent/15" : "size-2.5 bg-surface"
              }`}
              style={{ left: `${x}%`, bottom: `${100 - y}%` }}
            />
          ))}
          {/* Подпись только у пика — остальные значения в подсказке и таблице */}
          {hover === null && days[peak].dialogs > 0 && (
            <span
              className="absolute -translate-x-1/2 -translate-y-full pb-2 text-xs font-semibold text-ink tabular-nums"
              style={{ left: `${pts[peak][0]}%`, top: `${pts[peak][1]}%` }}
            >
              {days[peak].dialogs}
            </span>
          )}
          {/* Зоны наведения шире точки: вся высота дня */}
          <div className="absolute inset-0 flex">
            {days.map((d, i) => (
              <div key={d.date} className="relative h-full flex-1" onMouseEnter={() => setHover(i)}>
                {hover === i && (
                  <div
                    className={`pointer-events-none absolute bottom-full z-10 mb-2 w-max rounded-xl border border-line bg-surface px-3 py-2 text-xs shadow-lg ${
                      i < days.length / 2 ? "left-1/2" : "right-1/2"
                    }`}
                  >
                    <p className="font-medium text-ink">{dayMonth.format(asDate(d.date))}</p>
                    <p className="mt-0.5 text-ink-2">
                      {d.dialogs} {plural(d.dialogs, ["диалог", "диалога", "диалогов"])} · {d.questions}{" "}
                      {plural(d.questions, ["вопрос", "вопроса", "вопросов"])}
                    </p>
                    {d.questions > 0 && <p className="text-ink-2">бот ответил сам на {d.answered}</p>}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
      {/* День недели и число — в две строки: семь подписей помещаются и на телефоне */}
      <div className="mt-2.5 flex pl-7">
        {days.map((d, i) => {
          const date = asDate(d.date);
          const today = i === days.length - 1;
          return (
            <span
              key={d.date}
              className={`flex flex-1 flex-col items-center text-[11px] leading-tight ${
                today ? "font-semibold text-accent" : "text-ink-3"
              }`}
              title={today ? "Сегодня" : undefined}
            >
              <span>{weekday.format(date)}</span>
              <span className={today ? "" : "text-ink-2"}>{date.getDate()}</span>
            </span>
          );
        })}
      </div>
      <details className="mt-3 text-xs text-ink-2">
        <summary className="cursor-pointer text-ink-3 hover:text-ink-2">Таблицей</summary>
        <table className="mt-2 w-full text-left tabular-nums">
          <thead className="text-ink-3">
            <tr>
              <th className="py-1 font-normal">День</th>
              <th className="py-1 text-right font-normal">Диалоги</th>
              <th className="py-1 text-right font-normal">Вопросы</th>
              <th className="py-1 text-right font-normal">С ответом</th>
            </tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr key={d.date} className="border-t border-line">
                <td className="py-1">{dayMonth.format(asDate(d.date))}</td>
                <td className="py-1 text-right">{d.dialogs}</td>
                <td className="py-1 text-right">{d.questions}</td>
                <td className="py-1 text-right">{d.answered}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

function TopicsChart({ topics }: { topics: Analytics["topics"] }) {
  if (!topics.length) return <p className="py-6 text-center text-sm text-ink-3">Вопросов пока не было</p>;
  const max = Math.max(...topics.map((t) => t.count));
  const total = topics.reduce((sum, t) => sum + t.count, 0);
  return (
    <ol className="space-y-3">
      {topics.map((t) => (
        <li key={t.topic} title={`${t.label}: ${t.count}`}>
          <div className="flex items-baseline gap-2 text-sm">
            <span className="min-w-0 flex-1 truncate text-ink">{t.label}</span>
            <span className="font-medium text-ink tabular-nums">{t.count}</span>
            <span className="w-9 text-right text-xs text-ink-3 tabular-nums">
              {Math.round((t.count / total) * 100)}%
            </span>
          </div>
          {/* Тонкая полоса на сером треке: длина — число вопросов относительно самой частой темы */}
          <div className="mt-1.5 h-1.5 rounded-full bg-sunken">
            <div
              className="grow h-full rounded-full bg-accent"
              style={{ width: `${(t.count / max) * 100}%`, minWidth: 6 }}
            />
          </div>
        </li>
      ))}
    </ol>
  );
}

export function AnalyticsView() {
  const { data } = useSWR("analytics", api.analytics, { refreshInterval: 15000 });
  // Тот же счётчик, что в меню и на странице «Бот не смог ответить»: вопросы, которые ещё не разобраны
  const { data: unanswered } = useSWR(["unanswered", "open"], () => api.unanswered("open"));
  const open = unanswered?.open ?? 0;

  return (
    <div className="mx-auto max-w-5xl px-4 py-5 sm:px-6 sm:py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Аналитика</h1>
      <p className="mt-1 flex max-w-2xl items-start gap-1.5 text-sm leading-relaxed text-ink-2">
        За последние 7 дней по клиентам в Telegram: вымышленные демо-диалоги и ваш подключённый чат. Тестовый чат в
        статистику не входит.
      </p>

      {!data ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-24 rounded-2xl" />
          ))}
        </div>
      ) : (
        <>
          <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat
              label="Диалогов за неделю"
              value={data.dialogs}
              hint={`${data.questions} ${plural(data.questions, ["вопрос", "вопроса", "вопросов"])}`}
            />
            <Stat
              label="Бот ответил сам"
              value={data.answered_share === null ? "—" : `${Math.round(data.answered_share * 100)}%`}
              hint={`${data.answered} из ${data.questions}`}
            />
            <Stat
              label="Время ответа"
              value={data.median_ms === null ? "—" : formatSeconds(data.median_ms)}
              hint="медиана"
            />
            <Stat
              label="Заявок на запись"
              value={data.bookings}
              hint={`${data.operator_requests} ${plural(data.operator_requests, ["вызов", "вызова", "вызовов"])} администратора`}
              href="/admin/bookings"
            />
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[1.4fr_1fr]">
            <Panel className="p-4 sm:p-5">
              <h2 className="text-sm font-semibold text-ink">Диалоги по дням</h2>
              <p className="mt-0.5 mb-6 text-xs text-ink-3">Сколько клиентов написали боту в каждый из дней</p>
              <DaysChart days={data.days} />
            </Panel>
            <Panel className="p-4 sm:p-5">
              <h2 className="text-sm font-semibold text-ink">Топ тем</h2>
              <p className="mt-0.5 mb-4 text-xs text-ink-3">О чём спрашивают — тему определяет нейросеть при ответе</p>
              <TopicsChart topics={data.topics} />
              {open > 0 && (
                <Link
                  href="/admin/unanswered"
                  className="mt-5 flex items-center gap-2 rounded-xl bg-warn-soft px-3 py-2 text-xs text-ink-2 hover:text-ink"
                >
                  <Info className="size-3.5 shrink-0 text-warn" />
                  {open} {plural(open, ["вопрос", "вопроса", "вопросов"])} без ответа ждут разбора — посмотреть, чего не
                  хватает в базе
                  <ArrowUpRight className="ml-auto size-3.5 shrink-0" />
                </Link>
              )}
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
