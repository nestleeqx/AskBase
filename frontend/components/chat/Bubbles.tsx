"use client";

import { CalendarCheck, ChevronDown, Headset, UserRound } from "lucide-react";
import { useState } from "react";
import { formatSeconds, formatTime } from "@/lib/format";
import type { ChatMessage, Trace } from "@/lib/types";
import { DocIcon } from "../documents/DocIcon";

/** С какой стороны сообщения бота: в тестовом чате вы — клиент (бот слева),
 *  в «Диалогах» вы — клиника (бот и администратор справа, клиент слева). */
export type Side = "left" | "right";

function TraceDetails({ trace, question }: { trace: Trace; question?: string }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="mt-2 rounded-xl border border-line bg-surface p-3 text-left text-xs text-ink-2">
      <p className="font-medium text-ink">{trace.reason_label}</p>
      {question && trace.query !== question && (
        <p className="mt-1">
          С учётом диалога искал: <span className="text-ink">«{trace.query}»</span>
        </p>
      )}
      <p className="mt-1 text-ink-3">
        Поиск {formatSeconds(trace.search_ms)}
        {trace.llm_ms > 0 && ` · нейросеть ${formatSeconds(trace.llm_ms)}`}
        {trace.cached && " · ответ из кеша"}
      </p>
      {trace.hits.length > 0 && (
        <ol className="mt-2.5 space-y-1.5">
          {trace.hits.map((hit) => (
            <li key={hit.rank}>
              <button
                type="button"
                onClick={() => setOpen(open === hit.rank ? null : hit.rank)}
                className={`w-full rounded-lg border px-2.5 py-2 text-left transition-colors ${
                  hit.used ? "border-accent/40 bg-accent-soft/60" : "border-line hover:bg-sunken"
                }`}
              >
                <span className="flex items-center gap-2">
                  <span className="w-4 shrink-0 text-ink-3 tabular-nums">{hit.rank}</span>
                  <span className="min-w-0 flex-1 truncate text-ink">
                    {hit.document.title}
                    {hit.heading && hit.heading !== hit.document.title && (
                      <span className="text-ink-3"> · {hit.heading}</span>
                    )}
                  </span>
                  {hit.used && (
                    <span className="shrink-0 rounded-md bg-accent px-1.5 py-px text-[10px] font-semibold text-white">
                      в ответе
                    </span>
                  )}
                  <span className="shrink-0 text-ink-3 tabular-nums" title="Близость к вопросу по смыслу">
                    {hit.similarity.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </span>
                {open === hit.rank && (
                  <span className="mt-2 block text-[13px] leading-relaxed whitespace-pre-line text-ink">
                    {hit.text}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

const WRAP = { left: "items-start", right: "ml-auto items-end" } as const;
const CORNER = { left: "rounded-tl-md", right: "rounded-tr-md" } as const;

export function BotBubble({
  message,
  question,
  side = "left",
  showTime = false,
}: {
  message: ChatMessage;
  question?: string;
  side?: Side;
  showTime?: boolean;
}) {
  const [details, setDetails] = useState(false);

  if (message.reason === "booking") return <BookingNote message={message} side={side} />;

  const handoff = message.answered === false;
  return (
    <div className={`rise flex max-w-[92%] flex-col sm:max-w-[80%] ${WRAP[side]}`}>
      <div
        className={`rounded-2xl ${CORNER[side]} border px-4 py-3 text-sm leading-relaxed ${
          handoff ? "border-warn/25 bg-warn-soft" : "border-line bg-surface"
        }`}
      >
        {handoff && (
          <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-warn">
            <UserRound className="size-3.5" />
            Вопрос передан администратору
          </p>
        )}
        {message.reason === "operator" && (
          <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-warn">
            <Headset className="size-3.5" />
            Клиент позвал администратора
          </p>
        )}
        <p className="whitespace-pre-line text-ink">{message.text}</p>
        {message.sources.length > 0 && (
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5 border-t border-line pt-2.5">
            <span className="text-xs text-ink-3">{message.sources.length > 1 ? "Источники:" : "Источник:"}</span>
            {message.sources.map((s) => (
              <span
                key={s.id || s.title}
                className="inline-flex items-center gap-1.5 rounded-lg bg-sunken py-0.5 pr-2 pl-0.5 text-xs font-medium text-ink"
              >
                <span className="scale-75">
                  <DocIcon kind={s.kind} size="sm" />
                </span>
                {s.title}
              </span>
            ))}
          </div>
        )}
      </div>
      {(message.trace || showTime) && (
        <div className={`mt-1 w-full px-1 ${side === "right" ? "text-right" : ""}`}>
          <div
            className={`flex flex-wrap items-center gap-x-2 text-xs text-ink-3 ${side === "right" ? "justify-end" : ""}`}
          >
            {[
              showTime && `Бот · ${formatTime(message.created_at)}`,
              message.latency_ms != null && `ответ за ${formatSeconds(message.latency_ms)}`,
              message.trace && message.topic_label,
            ]
              .filter(Boolean)
              .join(" · ")}
            {message.trace && (
              <button
                type="button"
                onClick={() => setDetails((d) => !d)}
                className="inline-flex items-center gap-0.5 font-medium text-accent hover:underline"
              >
                · как бот искал ответ
                <ChevronDown className={`size-3.5 transition-transform ${details ? "rotate-180" : ""}`} />
              </button>
            )}
          </div>
          {details && message.trace && <TraceDetails trace={message.trace} question={question} />}
        </div>
      )}
    </div>
  );
}

// Сообщения бота о записи: начало строки — что произошло (см. BOOKING_NOTES в bot.py)
const BOOKING_NOTES: [prefix: string, title: string, done: boolean][] = [
  ["Заявка на запись:", "Бот принял заявку на запись", true],
  ["Заявка изменена:", "Клиент изменил заявку на запись", true],
  ["Запись без изменений:", "Клиент оставил запись как есть", false],
  ["Клиент отменил запись по шагам.", "Клиент отменил запись по шагам", false],
  ["Клиент отменил запись:", "Клиент отменил запись", false],
];

function BookingNote({ message, side }: { message: ChatMessage; side: Side }) {
  const [prefix, title, done] = BOOKING_NOTES.find(([p]) => message.text.startsWith(p)) ?? BOOKING_NOTES[0];
  const text = message.text.startsWith(prefix) ? message.text.slice(prefix.length).trim() : message.text;
  return (
    <div className={`rise flex max-w-[92%] flex-col sm:max-w-[80%] ${WRAP[side]}`}>
      <div
        className={`flex items-start gap-2.5 rounded-2xl border px-4 py-3 text-sm ${
          done ? "border-success/25 bg-success-soft" : "border-line bg-sunken"
        }`}
      >
        <CalendarCheck className={`mt-0.5 size-4 shrink-0 ${done ? "text-success" : "text-ink-3"}`} />
        <div>
          <p className="font-medium text-ink">{title}</p>
          {text && <p className="mt-0.5 leading-relaxed text-ink-2">{text}</p>}
        </div>
      </div>
      <p className="mt-1 px-1 text-xs text-ink-3">{formatTime(message.created_at)}</p>
    </div>
  );
}

export function OperatorBubble({ message }: { message: ChatMessage }) {
  return (
    <div className="rise ml-auto flex max-w-[92%] flex-col items-end sm:max-w-[80%]">
      <div className="rounded-2xl rounded-tr-md bg-accent px-4 py-2.5 text-sm leading-relaxed whitespace-pre-line text-white">
        {message.text}
      </div>
      <p className="mt-1 flex items-center gap-1 px-1 text-xs text-ink-3">
        <Headset className="size-3" />
        Администратор · {formatTime(message.created_at)}
      </p>
    </div>
  );
}

export function UserBubble({ text, side = "right", time }: { text: string; side?: Side; time?: string }) {
  if (side === "right")
    return (
      <div className="rise ml-auto max-w-[85%] rounded-2xl rounded-tr-md bg-accent px-4 py-2.5 text-sm leading-relaxed whitespace-pre-line text-white sm:max-w-[75%]">
        {text}
      </div>
    );
  return (
    <div className="rise flex max-w-[85%] flex-col items-start sm:max-w-[75%]">
      <div className="rounded-2xl rounded-tl-md bg-sunken px-4 py-2.5 text-sm leading-relaxed whitespace-pre-line text-ink">
        {text}
      </div>
      {time && <p className="mt-1 px-1 text-xs text-ink-3">Клиент · {formatTime(time)}</p>}
    </div>
  );
}

export function Typing() {
  return (
    <div className="fade-in flex w-fit items-center gap-1 rounded-2xl rounded-tl-md border border-line bg-surface px-4 py-3.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="size-1.5 animate-bounce rounded-full bg-ink-3"
          style={{ animationDelay: `${i * 140}ms` }}
        />
      ))}
    </div>
  );
}
