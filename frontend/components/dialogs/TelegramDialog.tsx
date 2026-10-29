"use client";

import { CheckCircle2, Loader2, Send } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { TelegramStatus } from "@/lib/types";
import { useToast } from "../Toast";
import { Button } from "../ui";

const STEPS = [
  "Откройте бота по кнопке ниже и нажмите «Старт» — чат подключится к этой админке.",
  "Задайте боту вопросы как клиент клиники. Спросите и то, чего нет в документах, — бот передаст вопрос администратору.",
  "Ваш диалог появится в списке. Ответьте себе как администратор: сообщение придёт в Telegram, а бот в этом чате замолчит на 30 минут.",
];

/** Статус бота — общий для страницы и окна. */
export function useTelegram(poll = false) {
  return useSWR<TelegramStatus>("telegram", api.telegram, {
    refreshInterval: poll ? 2000 : 0,
    revalidateOnFocus: true,
  });
}

export function TelegramDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const titleId = useId();
  const [link, setLink] = useState<{ url: string } | { error: string } | null>(null);
  const { data: status } = useTelegram();
  const linked = !!status?.linked;
  // Пока чат не привязан, опрашиваем статус: привязка случится в Telegram, а не здесь
  useTelegram(!!status && !linked);

  // Чат привязался, пока окно открыто, — сообщаем об этом
  const wasLinked = useRef<boolean | null>(null);
  useEffect(() => {
    if (!status) return;
    if (wasLinked.current === false && linked) toast.ok("Telegram подключён — ваш диалог появится в списке");
    wasLinked.current = linked;
  }, [status, linked, toast]);

  useEffect(() => {
    let alive = true;
    api.telegramLink().then(
      (l) => alive && setLink(l),
      (e: Error) => alive && setLink({ error: e.message }),
    );
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    const overflow = root.style.overflow;
    root.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      root.style.overflow = overflow;
    };
  }, [onClose]);

  const url = link && "url" in link ? link.url : null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4">
      <div className="fade-in absolute inset-0 bg-ink/30 backdrop-blur-[2px]" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="pop relative w-full max-w-lg rounded-t-3xl border border-line bg-surface p-5 shadow-[0_30px_60px_-20px_rgba(16,32,31,.35)] sm:rounded-3xl sm:p-6"
      >
        <div className="flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl bg-[#229ED9]/10 text-[#229ED9]">
            <Send className="size-4.5" />
          </span>
          <div>
            <h2 id={titleId} className="text-base font-semibold">
              Telegram-бот клиники
            </h2>
            {status?.username && <p className="text-xs text-ink-3">@{status.username}</p>}
          </div>
        </div>

        {linked ? (
          <div className="mt-4 flex items-start gap-2.5 rounded-2xl border border-success/20 bg-success-soft px-4 py-3">
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />
            <p className="text-sm text-ink">Ваш Telegram подключён: переписка с ботом видна в «Диалогах».</p>
          </div>
        ) : (
          <p className="mt-3 text-sm leading-relaxed text-ink-2">
            Напишите боту как клиент — и посмотрите, как выглядит ваш диалог в админке и как администратор подключается
            к разговору.
          </p>
        )}

        <ol className="mt-4 space-y-3">
          {STEPS.map((step, i) => (
            <li
              key={step}
              className={`flex gap-3 text-sm leading-relaxed ${linked && i === 0 ? "text-ink-3" : "text-ink-2"}`}
            >
              <span
                className={`grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold ${
                  linked && i === 0 ? "bg-success-soft text-success" : "bg-sunken text-ink"
                }`}
              >
                {linked && i === 0 ? "✓" : i + 1}
              </span>
              {step}
            </li>
          ))}
        </ol>

        {link && "error" in link && <p className="mt-4 text-sm text-danger">{link.error}</p>}

        <div className="mt-6 flex flex-wrap items-center gap-2 sm:justify-end">
          {!linked && !(link && "error" in link) && (
            <p className="mr-auto flex items-center gap-1.5 text-xs whitespace-nowrap text-ink-3 max-sm:order-last max-sm:w-full max-sm:justify-center">
              <Loader2 className="size-3.5 animate-spin" />
              Ждём «Старт» в боте
            </p>
          )}
          <Button className="max-sm:flex-1" onClick={onClose}>
            {linked ? "Готово" : "Закрыть"}
          </Button>
          {/* Ссылка, а не кнопка с window.open: открытие после запроса блокируют браузеры */}
          <a
            href={url ?? undefined}
            target="_blank"
            rel="noreferrer"
            aria-disabled={!url}
            className={`inline-flex h-9 items-center justify-center gap-1.5 rounded-xl px-4 text-sm font-medium whitespace-nowrap text-white transition-colors max-sm:flex-1 ${
              url ? "bg-[#229ED9] hover:bg-[#1c8cc2]" : "pointer-events-none bg-[#229ED9]/50"
            }`}
          >
            {url ? <Send className="size-4" /> : <Loader2 className="size-4 animate-spin" />}
            Открыть бота
          </a>
        </div>
      </div>
    </div>
  );
}
