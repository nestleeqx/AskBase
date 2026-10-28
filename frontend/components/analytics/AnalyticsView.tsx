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
      <p className="text-xs text-ink-2">{label}</p>
      <p className="mt-1.5 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-ink-3">{hint}</p>}
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

function DaysChart({ days }: { days: AnalyticsDay[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...days.map((d) => d.dialogs));
  // Чистые деления оси: 0, половина, максимум, округлённый вверх
  const top = max <= 4 ? max : Math.ceil(max / 2) * 2;
  const ticks = [top, top / 2, 0];

  return (
    <div>
      <div className="relative h-48 pl-7">
        {ticks.map((t) => (
          <div
            key={t}
            className="absolute right-0 left-7 border-t border-line"
            style={{ bottom: `${(t / top) * 100}%` }}
          >
            <span className="absolute -top-2 -left-7 w-5 text-right text-[11px] text-ink-3 tabular-nums">
              {Number.isInteger(t) ? t : ""}
            </span>
          </div>
        ))}
        <div className="absolute inset-0 left-7 flex items-end">
          {days.map((d, i) => (
            <div
              key={d.date}
              className="relative flex h-full flex-1 items-end justify-center"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            >
              {d.dialogs > 0 && (
                <div
                  className={`relative w-full max-w-6 rounded-t-[4px] transition-opacity ${
                    hover !== null && hover !== i ? "opacity-50" : ""
                  }`}
                  style={{ height: `${(d.dialogs / top) * 100}%`, background: "var(--color-accent)" }}
                >
                  <span className="absolute -top-5 left-1/2 -translate-x-1/2 text-xs font-medium text-ink tabular-nums">
                    {d.dialogs}
                  </span>
                </div>
              )}
              {hover === i && (
                <div className="pointer-events-none absolute bottom-full z-10 mb-2 w-max rounded-xl border border-line bg-surface px-3 py-2 text-xs shadow-lg">
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
      <div className="mt-2 flex pl-7">
        {days.map((d) => {
          const date = asDate(d.date);
          return (
            <span key={d.date} className="flex-1 text-center text-[11px] text-ink-3">
              {weekday.format(date)} {date.getDate()}
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
  return (
    <ol className="space-y-2.5">
      {topics.map((t, i) => (
        <li key={t.topic} className="grid grid-cols-[1.25rem_10.5rem_1fr] items-center gap-2 text-sm">
          <span className="text-xs text-ink-3 tabular-nums">{i + 1}</span>
          <span className="truncate text-ink">{t.label}</span>
          <span className="flex items-center gap-2" title={`${t.label}: ${t.count}`}>
            <span
              className="h-3 rounded-r-[4px]"
              style={{ width: `${(t.count / max) * 100}%`, background: "var(--color-accent)", minWidth: 4 }}
            />
            <span className="text-xs text-ink-2 tabular-nums">{t.count}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

export function AnalyticsView() {
  const { data } = useSWR("analytics", api.analytics, { refreshInterval: 15000 });

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
              hint={`позвали администратора: ${data.operator_requests}`}
              href="/admin/bookings"
            />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <Panel className="p-4 sm:p-5">
              <h2 className="text-sm font-semibold text-ink">Диалоги по дням</h2>
              <p className="mt-0.5 mb-6 text-xs text-ink-3">Сколько клиентов написали боту в каждый из дней</p>
              <DaysChart days={data.days} />
            </Panel>
            <Panel className="p-4 sm:p-5">
              <h2 className="text-sm font-semibold text-ink">Топ тем</h2>
              <p className="mt-0.5 mb-4 text-xs text-ink-3">О чём спрашивают — тему определяет нейросеть при ответе</p>
              <TopicsChart topics={data.topics} />
              {data.unanswered > 0 && (
                <Link
                  href="/admin/unanswered"
                  className="mt-5 flex items-center gap-2 rounded-xl bg-warn-soft px-3 py-2 text-xs text-ink-2 hover:text-ink"
                >
                  <Info className="size-3.5 shrink-0 text-warn" />
                  {data.unanswered} {plural(data.unanswered, ["вопрос", "вопроса", "вопросов"])} без ответа за неделю —
                  посмотреть, чего не хватает в базе
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
