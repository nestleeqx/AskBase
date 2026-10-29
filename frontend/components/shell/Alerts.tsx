"use client";

import { Bell, BellOff } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useSyncExternalStore } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { Booking, DialogSummary } from "@/lib/types";
import { useToast } from "../Toast";

const SOUND_KEY = "askbase:sound";
const listeners = new Set<() => void>();

function soundOn() {
  try {
    return localStorage.getItem(SOUND_KEY) !== "off";
  } catch {
    return true;
  }
}

function setSound(on: boolean) {
  try {
    localStorage.setItem(SOUND_KEY, on ? "on" : "off");
  } catch {
    // Без localStorage звук просто останется включённым
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

let audio: AudioContext | null = null;

/** Короткий двухнотный сигнал, без файла: Web Audio. До первого клика по странице браузер может
 *  его заглушить — тогда остаются всплывашка и счётчик во вкладке. */
function chime() {
  try {
    audio ??= new AudioContext();
    void audio.resume();
    const start = audio.currentTime;
    [880, 1318.5].forEach((freq, i) => {
      const osc = audio!.createOscillator();
      const gain = audio!.createGain();
      const t = start + i * 0.16;
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.18, t + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.45);
      osc.connect(gain).connect(audio!.destination);
      osc.start(t);
      osc.stop(t + 0.5);
    });
  } catch {
    // Нет Web Audio — без звука
  }
}

/** Что клиент сделал с заявкой: создал (время действия совпадает с созданием), отменил или изменил. */
function bookingText(b: Booking) {
  if (b.status === "cancelled") return `${b.name} отменяет запись`;
  const created = Math.abs(Date.parse(b.client_changed_at) - Date.parse(b.created_at)) < 5000;
  return created ? `новая заявка — ${b.name}` : `${b.name} изменяет заявку`;
}

// Опрос и в фоновой вкладке: админка обычно открыта рядом с другими делами
const POLL = { refreshInterval: 10000, refreshWhenHidden: true };

/** Сигналы о том, что нужен человек: клиент позвал администратора или бот не нашёл ответа,
 *  новая заявка на запись. На каждое сообщение клиента не сигналим — бот с ними справляется сам. */
export function useAlerts() {
  const toast = useToast();
  const { data: dialogs } = useSWR(["dialogs", "", false], () => api.dialogs(), POLL);
  const { data: bookings } = useSWR("bookings", api.bookings, POLL);
  const waiting = dialogs?.waiting;
  const fresh = bookings?.new;
  // Последний раз, когда клиенту понадобился человек (позвал администратора, бот не нашёл ответа,
  // написал, пока отвечает администратор). Не число ждущих: клиент, который уже ждёт, может позвать
  // снова — число не изменится, а сигнал нужен. И не время любого сообщения: служебные сообщения
  // о записи в ждущем диалоге — не повод звать человека, о заявках сигналит отдельное событие
  const latestWaiting = dialogs?.dialogs.reduce<DialogSummary | null>(
    (top, d) => (d.attention_at && (!top || d.attention_at > top.attention_at!) ? d : top),
    null,
  );
  const attention = dialogs ? (latestWaiting?.attention_at ?? "") : undefined;
  // Последнее действие клиента с заявкой: создал, изменил или отменил. Подтверждение и отмена
  // администратором его не меняют — о своих же действиях админка не сигналит
  const latestBooking = bookings?.bookings.reduce<Booking | null>(
    (top, b) => (!top || b.client_changed_at > top.client_changed_at ? b : top),
    null,
  );
  const bookingAction = bookings ? (latestBooking?.client_changed_at ?? "") : undefined;
  const pathname = usePathname();
  const seen = useRef<{ attention?: string; bookingAction?: string }>({});

  useEffect(() => {
    const before = seen.current;
    const events: { text: string; href: string }[] = [];
    // Первую загрузку не считаем: сигналим только о том, что появилось, пока админка открыта
    if (attention && before.attention !== undefined && attention > before.attention)
      events.push({
        text: `Диалоги: ${latestWaiting?.title ?? "клиент"} ждёт администратора`,
        href: "/admin/dialogs",
      });
    if (latestBooking && bookingAction && before.bookingAction !== undefined && bookingAction > before.bookingAction)
      events.push({ text: `Заявки на запись: ${bookingText(latestBooking)}`, href: "/admin/bookings" });
    seen.current = {
      attention: attention ?? before.attention,
      bookingAction: bookingAction ?? before.bookingAction,
    };
    if (!events.length) return;
    // Звук — всегда. Всплывашка — только если событие с другой страницы: в «Диалогах» новый
    // ждущий клиент и так виден в списке, подсказка «откуда» не нужна
    events.filter((e) => !pathname.startsWith(e.href)).forEach((e) => toast.info(e.text, e.href));
    if (soundOn()) chime();
    // toast и подписи — новые на каждый рендер, а сигналить нужно только по новым событиям
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attention, bookingAction]);

  // Счётчик во вкладке браузера: видно, даже когда открыта другая вкладка. Next.js при переходе
  // между страницами ставит свой заголовок — следим за ним и возвращаем число
  const total = (waiting ?? 0) + (fresh ?? 0);
  useEffect(() => {
    const apply = () => {
      const base = document.title.replace(/^\(\d+\) /, "");
      const next = total ? `(${total}) ${base}` : base;
      if (document.title !== next) document.title = next;
    };
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.head, { subtree: true, childList: true, characterData: true });
    return () => observer.disconnect();
  }, [total]);
}

export function SoundToggle() {
  const on = useSyncExternalStore(subscribe, soundOn, () => true);
  return (
    <button
      type="button"
      onClick={() => {
        setSound(!on);
        if (!on) chime();
      }}
      aria-pressed={on}
      title={on ? "Звук уведомлений включён" : "Звук уведомлений выключен"}
      aria-label={on ? "Выключить звук уведомлений" : "Включить звук уведомлений"}
      className="grid size-9 place-items-center rounded-xl text-ink-3 transition-colors hover:bg-sunken hover:text-ink"
    >
      {on ? <Bell className="size-4" /> : <BellOff className="size-4" />}
    </button>
  );
}
