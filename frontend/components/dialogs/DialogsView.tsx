"use client";

import { ArrowLeft, Bot, CalendarCheck, Headset, Inbox, Search, Send, SendHorizontal } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { formatShortTime, formatTime, plural } from "@/lib/format";
import type { DialogDetail, DialogSummary } from "@/lib/types";
import { BotBubble, OperatorBubble, UserBubble } from "../chat/Bubbles";
import { useToast } from "../Toast";
import { Button } from "../ui";
import { TelegramDialog, useTelegram } from "./TelegramDialog";

const AVATAR_COLORS = ["#0d9488", "#0891b2", "#6d4ae0", "#c2410c", "#be185d", "#4d7c0f", "#a16207", "#1d4ed8"];

function Avatar({ name, size = "md" }: { name: string; size?: "md" | "lg" }) {
  const hash = [...name].reduce((a, c) => a + c.charCodeAt(0), 0);
  return (
    <span
      className={`grid shrink-0 place-items-center rounded-full font-semibold text-white ${
        size === "lg" ? "size-10 text-base" : "size-9 text-sm"
      }`}
      style={{ background: AVATAR_COLORS[hash % AVATAR_COLORS.length] }}
      aria-hidden
    >
      {name.replace(/^@/, "").charAt(0).toUpperCase()}
    </span>
  );
}

function operatorActive(d: DialogSummary) {
  return !!d.operator_until && new Date(d.operator_until) > new Date();
}

function StatusChip({ dialog }: { dialog: DialogSummary }) {
  if (operatorActive(dialog))
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-accent-soft px-1.5 py-px text-[11px] font-medium whitespace-nowrap text-accent-ink">
        <Headset className="size-3" />
        Отвечает администратор
      </span>
    );
  if (dialog.waiting_since)
    return (
      <span className="rounded-md bg-warn-soft px-1.5 py-px text-[11px] font-medium whitespace-nowrap text-warn">
        Ждёт ответа
      </span>
    );
  return null;
}

const SPEAKER = { user: "", bot: "Бот: ", operator: "Администратор: " } as const;

function DialogItem({ dialog, active, onSelect }: { dialog: DialogSummary; active: boolean; onSelect: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? "true" : undefined}
        className={`flex w-full gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
          active ? "bg-accent-soft" : "hover:bg-sunken"
        }`}
      >
        <Avatar name={dialog.title} />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-2">
            <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{dialog.title}</span>
            <span className="shrink-0 text-[11px] text-ink-3 tabular-nums">{formatShortTime(dialog.updated_at)}</span>
          </span>
          {dialog.last && (
            <span className="mt-0.5 line-clamp-1 text-[13px] text-ink-2">
              <span className="text-ink-3">{SPEAKER[dialog.last.role]}</span>
              {dialog.last.text}
            </span>
          )}
          <span className="mt-1 flex flex-wrap items-center gap-1.5">
            <StatusChip dialog={dialog} />
            {dialog.demo ? (
              <span className="text-[11px] text-ink-3">пример</span>
            ) : (
              <span className="rounded-md bg-info-soft px-1.5 py-px text-[11px] font-medium text-info">ваш диалог</span>
            )}
          </span>
        </span>
      </button>
    </li>
  );
}

function Composer({ dialog, onChange }: { dialog: DialogDetail; onChange: (d: DialogDetail) => void }) {
  const toast = useToast();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<"send" | "release" | null>(null);
  const active = operatorActive(dialog);

  if (dialog.demo)
    return (
      <p className="border-t border-line bg-surface px-4 py-3 text-center text-xs leading-relaxed text-ink-3 sm:px-5">
        Это пример диалога — ответить в нём нельзя. Подключите свой Telegram и напишите боту: ваш диалог появится в
        списке, и в нём можно ответить как администратор.
      </p>
    );

  async function send(e: FormEvent) {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    setBusy("send");
    try {
      onChange(await api.reply(dialog.id, value));
      setText("");
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(null);
    }
  }

  async function release() {
    setBusy("release");
    try {
      onChange(await api.release(dialog.id));
      toast.ok("Бот снова отвечает клиенту");
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="border-t border-line bg-surface p-3 sm:p-4">
      {active && (
        <div className="mb-2.5 flex flex-wrap items-center gap-2 rounded-xl bg-accent-soft px-3 py-2 text-xs text-accent-ink">
          <Headset className="size-3.5 shrink-0" />
          <span className="flex-1">Бот молчит до {formatTime(dialog.operator_until!)} — клиенту отвечаете вы.</span>
          <Button
            size="sm"
            variant="secondary"
            loading={busy === "release"}
            onClick={release}
            icon={<Bot className="size-3.5" />}
          >
            Вернуть боту
          </Button>
        </div>
      )}
      <form onSubmit={send} className="flex items-end gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
          rows={1}
          maxLength={2000}
          placeholder="Ответить клиенту как администратор…"
          aria-label="Ответ клиенту"
          className="max-h-40 min-h-11 min-w-0 flex-1 resize-none rounded-xl border border-line bg-surface px-3.5 py-2.5 text-sm outline-none [field-sizing:content] placeholder:text-ink-3 focus:border-accent/40 focus:ring-4 focus:ring-accent-soft"
        />
        <Button
          type="submit"
          variant="primary"
          className="h-11 w-11 shrink-0 px-0 sm:w-auto sm:px-4"
          loading={busy === "send"}
          disabled={!text.trim() || !!busy}
          aria-label="Отправить"
          icon={busy === "send" ? undefined : <SendHorizontal className="size-4" />}
        >
          <span className="max-sm:hidden">Отправить</span>
        </Button>
      </form>
      {!active && (
        <p className="mt-1.5 text-[11px] text-ink-3">
          Ответ придёт клиенту в Telegram от имени бота с пометкой «Администратор клиники». Бот в этом чате замолчит на
          30 минут.
        </p>
      )}
    </div>
  );
}

function Thread({ id, onBack }: { id: string; onBack: () => void }) {
  const { mutate: mutateAll } = useSWRConfig();
  const { data, error, mutate } = useSWR(["dialog", id], () => api.dialog(id), { refreshInterval: 3000 });
  const scrollRef = useRef<HTMLDivElement>(null);
  const count = data?.messages.length ?? 0;

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight });
  }, [id, count]);

  if (error)
    return (
      <div className="grid flex-1 place-items-center p-6 text-center text-sm text-ink-2">
        <div>
          <p>{error.message}</p>
          <Button className="mt-3" onClick={onBack}>
            К списку
          </Button>
        </div>
      </div>
    );
  if (!data) return <div className="skeleton m-4 flex-1 rounded-2xl" />;

  function changed(d: DialogDetail) {
    mutate(d, { revalidate: false });
    // Статус диалога поменялся — обновляем список и бейдж в меню
    mutateAll((key) => Array.isArray(key) && key[0] === "dialogs");
  }

  return (
    <>
      <div className="flex items-center gap-3 border-b border-line px-3 py-3 sm:px-5">
        <button
          type="button"
          onClick={onBack}
          aria-label="К списку диалогов"
          className="grid size-9 shrink-0 place-items-center rounded-lg text-ink-2 hover:bg-sunken lg:hidden"
        >
          <ArrowLeft className="size-4.5" />
        </button>
        <Avatar name={data.title} size="lg" />
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-ink">{data.title}</p>
          <p className="truncate text-xs text-ink-3">
            Telegram{data.username && ` · @${data.username}`} · {data.messages_count}{" "}
            {plural(data.messages_count, ["сообщение", "сообщения", "сообщений"])}
          </p>
        </div>
        <span className="max-sm:hidden">
          <StatusChip dialog={data} />
        </span>
      </div>

      {data.bookings.length > 0 && (
        <div className="flex flex-wrap gap-2 border-b border-line bg-success-soft/40 px-4 py-2 sm:px-5">
          {data.bookings.map((b) => (
            <Link
              key={b.id}
              href="/admin/bookings"
              className="inline-flex items-center gap-1.5 text-xs text-ink-2 hover:text-ink"
            >
              <CalendarCheck className="size-3.5 text-success" />
              Заявка на запись: {b.preferred_time} ·{" "}
              <span className="font-medium">
                {b.status === "new" ? "ждёт звонка" : b.status === "confirmed" ? "подтверждена" : "отменена"}
              </span>
            </Link>
          ))}
        </div>
      )}

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto bg-sunken/40 px-3 py-4 scrollbar-thin sm:px-5">
        {data.messages.map((m, i) =>
          m.role === "user" ? (
            <UserBubble key={m.id} text={m.text} side="left" time={m.created_at} />
          ) : m.role === "operator" ? (
            <OperatorBubble key={m.id} message={m} />
          ) : (
            <BotBubble key={m.id} message={m} question={data.messages[i - 1]?.text} side="right" showTime />
          ),
        )}
      </div>

      <Composer dialog={data} onChange={changed} />
    </>
  );
}

export function DialogsView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const selected = params.get("id");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [waitingOnly, setWaitingOnly] = useState(false);
  const [connect, setConnect] = useState(false);
  const { data: telegram } = useTelegram();

  // Поиск — после паузы в наборе, а не на каждую букву
  useEffect(() => {
    const t = setTimeout(() => setSearch(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);

  const { data } = useSWR(["dialogs", search, waitingOnly], () => api.dialogs(search, waitingOnly), {
    refreshInterval: 4000,
    keepPreviousData: true,
  });

  function select(id: string | null) {
    router.replace(id ? `${pathname}?id=${id}` : pathname, { scroll: false });
  }

  // На широком экране сразу открываем первый диалог, на телефоне — показываем список
  const first = data?.dialogs[0]?.id;
  useEffect(() => {
    if (!selected && first && window.matchMedia("(min-width: 1024px)").matches) {
      router.replace(`${pathname}?id=${first}`, { scroll: false });
    }
  }, [selected, first, pathname, router]);

  return (
    <div className="mx-auto flex h-[calc(100dvh-4rem)] max-w-6xl flex-col px-4 py-5 sm:px-6 sm:py-6">
      <div className={`mb-4 flex flex-wrap items-end justify-between gap-3 ${selected ? "max-lg:hidden" : ""}`}>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Диалоги</h1>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-ink-2">
            Переписка клиентов с ботом в Telegram. Если бот не нашёл ответа или клиент позвал человека, диалог ждёт
            администратора.
          </p>
        </div>
        {telegram?.enabled && (
          <Button
            onClick={() => setConnect(true)}
            icon={<Send className="size-4 text-[#229ED9]" />}
            title={telegram.linked ? "Ваш Telegram подключён" : undefined}
          >
            {telegram.linked ? "Открыть бота" : "Подключить свой Telegram"}
          </Button>
        )}
      </div>

      <div className="flex min-h-0 flex-1 gap-4">
        <section
          aria-label="Список диалогов"
          className={`flex min-h-0 w-full flex-col rounded-2xl border border-line bg-surface lg:w-[340px] lg:shrink-0 ${
            selected ? "max-lg:hidden" : ""
          }`}
        >
          <div className="space-y-2.5 border-b border-line p-3">
            <label className="relative block">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Имя клиента или текст сообщения"
                aria-label="Поиск по диалогам"
                className="h-9 w-full rounded-xl border border-line bg-surface pr-3 pl-9 text-sm outline-none placeholder:text-ink-3 focus:border-accent/40 focus:ring-4 focus:ring-accent-soft"
              />
            </label>
            <div className="flex gap-1 rounded-xl bg-sunken p-1 text-xs font-medium" role="tablist">
              {[
                [false, "Все"],
                [true, `Ждут ответа${data?.waiting ? ` · ${data.waiting}` : ""}`],
              ].map(([value, label]) => (
                <button
                  key={String(value)}
                  type="button"
                  role="tab"
                  aria-selected={waitingOnly === value}
                  onClick={() => setWaitingOnly(value as boolean)}
                  className={`h-7 flex-1 rounded-lg transition-colors ${
                    waitingOnly === value ? "bg-surface text-ink shadow-sm" : "text-ink-2 hover:text-ink"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2 scrollbar-thin">
            {!data ? (
              <div className="space-y-2 p-1">
                {[0, 1, 2, 3].map((i) => (
                  <div key={i} className="skeleton h-16 rounded-xl" />
                ))}
              </div>
            ) : data.dialogs.length === 0 ? (
              <p className="px-4 py-10 text-center text-sm text-ink-3">
                {search ? "Ничего не нашлось" : waitingOnly ? "Все клиенты получили ответ 👌" : "Диалогов пока нет"}
              </p>
            ) : (
              <ul className="space-y-0.5">
                {data.dialogs.map((d) => (
                  <DialogItem key={d.id} dialog={d} active={d.id === selected} onSelect={() => select(d.id)} />
                ))}
              </ul>
            )}
          </div>
        </section>

        <section
          aria-label="Переписка"
          className={`flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-line bg-surface ${
            selected ? "" : "max-lg:hidden"
          }`}
        >
          {selected ? (
            <Thread key={selected} id={selected} onBack={() => select(null)} />
          ) : (
            <div className="grid flex-1 place-items-center p-6 text-center text-sm text-ink-3">
              <div>
                <Inbox className="mx-auto mb-2 size-8 text-ink-3/60" />
                Выберите диалог слева
              </div>
            </div>
          )}
        </section>
      </div>

      {connect && <TelegramDialog onClose={() => setConnect(false)} />}
    </div>
  );
}
