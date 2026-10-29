"use client";

import { CalendarCheck, Check, MessageCircle, Phone, RotateCcw, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { formatTime } from "@/lib/format";
import type { Booking, BookingStatus } from "@/lib/types";
import { useToast } from "../Toast";
import { Button } from "../ui";

const STATUS: Record<BookingStatus, { label: string; className: string }> = {
  new: { label: "Ждёт звонка", className: "bg-warn-soft text-warn" },
  confirmed: { label: "Подтверждена", className: "bg-success-soft text-success" },
  cancelled: { label: "Отменена", className: "bg-sunken text-ink-3" },
};

const FILTERS: [BookingStatus | "all", string][] = [
  ["all", "Все"],
  ["new", "Новые"],
  ["confirmed", "Подтверждённые"],
  ["cancelled", "Отменённые"],
];

function BookingCard({ booking, onChange }: { booking: Booking; onChange: (b: Booking) => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<BookingStatus | null>(null);
  const status = STATUS[booking.status];

  async function set(next: BookingStatus) {
    setBusy(next);
    try {
      onChange(await api.setBooking(booking.id, next));
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(null);
    }
  }

  const rows: [string, string][] = [["Удобное время", booking.preferred_time]];
  if (booking.reason) rows.unshift(["Повод", booking.reason]);

  return (
    <li className="rise flex flex-col rounded-2xl border border-line bg-surface p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-sunken text-ink">
          <CalendarCheck className="size-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-ink">{booking.name}</p>
          <a
            href={`tel:${booking.phone.replace(/[^\d+]/g, "")}`}
            className="mt-0.5 inline-flex items-center gap-1 text-sm whitespace-nowrap text-accent hover:underline"
          >
            <Phone className="size-3.5" />
            {booking.phone}
          </a>
        </div>
        <span className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-medium ${status.className}`}>
          {status.label}
        </span>
      </div>

      <dl className="mt-3.5 mb-4 space-y-1.5 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="flex flex-col min-[400px]:flex-row min-[400px]:gap-2">
            <dt className="shrink-0 text-xs text-ink-3 min-[400px]:w-28 min-[400px]:text-sm">{label}</dt>
            <dd className="min-w-0 text-ink">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-auto flex flex-wrap items-center gap-2 border-t border-line pt-3.5 text-xs text-ink-3">
        <span className="mr-auto">
          {formatTime(booking.created_at)} · {booking.demo ? "пример" : "ваша заявка"}
        </span>
        <Link
          href={`/admin/dialogs?id=${booking.conversation_id}`}
          className="inline-flex items-center gap-1 font-medium text-ink-2 hover:text-ink"
        >
          <MessageCircle className="size-3.5" />
          Диалог
        </Link>
      </div>

      {!booking.demo && (
        <div className="mt-3 flex gap-2">
          {booking.status === "new" ? (
            <>
              <Button
                size="sm"
                variant="primary"
                className="flex-1"
                loading={busy === "confirmed"}
                disabled={!!busy}
                onClick={() => set("confirmed")}
                icon={<Check className="size-3.5" />}
              >
                Подтвердить
              </Button>
              <Button
                size="sm"
                className="flex-1"
                loading={busy === "cancelled"}
                disabled={!!busy}
                onClick={() => set("cancelled")}
                icon={<X className="size-3.5" />}
              >
                Отменить
              </Button>
            </>
          ) : (
            <>
              <Button
                size="sm"
                variant="ghost"
                loading={busy === "new"}
                disabled={!!busy}
                onClick={() => set("new")}
                icon={<RotateCcw className="size-3.5" />}
              >
                Вернуть в новые
              </Button>
              {/* Подтверждённую запись тоже можно отменить: клиент передумал или это дубль */}
              {booking.status === "confirmed" && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="ml-auto"
                  loading={busy === "cancelled"}
                  disabled={!!busy}
                  onClick={() => set("cancelled")}
                  icon={<X className="size-3.5" />}
                >
                  Отменить
                </Button>
              )}
            </>
          )}
        </div>
      )}
    </li>
  );
}

export function BookingsView() {
  const { data, mutate } = useSWR("bookings", api.bookings, { refreshInterval: 5000 });
  const [filter, setFilter] = useState<BookingStatus | "all">("all");
  const items = data?.bookings.filter((b) => filter === "all" || b.status === filter) ?? [];

  function changed(b: Booking) {
    if (!data) return;
    const bookings = data.bookings.map((x) => (x.id === b.id ? b : x));
    mutate({ bookings, new: bookings.filter((x) => x.status === "new").length });
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-5 sm:px-6 sm:py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Заявки на запись</h1>
      <p className="mt-1 max-w-2xl text-sm leading-relaxed text-ink-2">
        Бот собирает заявку в Telegram по шагам: имя, телефон, повод и удобное время. Администратор перезванивает
        клиенту и подтверждает запись.
      </p>

      <div className="mt-5 flex gap-1 overflow-x-auto rounded-xl bg-sunken p-1 text-xs font-medium scrollbar-none sm:w-fit">
        {FILTERS.map(([value, label]) => {
          const count =
            value === "all" ? data?.bookings.length : data?.bookings.filter((b) => b.status === value).length;
          return (
            <button
              key={value}
              type="button"
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
              className={`h-7 shrink-0 rounded-lg px-3 transition-colors ${
                filter === value ? "bg-surface text-ink shadow-sm" : "text-ink-2 hover:text-ink"
              }`}
            >
              {label}
              {!!count && <span className="ml-1 text-ink-3 tabular-nums">{count}</span>}
            </button>
          );
        })}
      </div>

      {!data ? (
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-56 rounded-2xl" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="mt-10 text-center text-sm text-ink-3">Заявок нет</p>
      ) : (
        <ul className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((b) => (
            <BookingCard key={b.id} booking={b} onChange={changed} />
          ))}
        </ul>
      )}
    </div>
  );
}
