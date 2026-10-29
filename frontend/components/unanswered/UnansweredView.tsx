"use client";

import { BookPlus, Check, CircleHelp, MessageCircle, RotateCcw, Send } from "lucide-react";
import Link from "next/link";
import { useCallback, useState, type FormEvent } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { formatTime } from "@/lib/format";
import type { UnansweredItem } from "@/lib/types";
import { LIST_PAGE, LoadMore } from "../LoadMore";
import { useToast } from "../Toast";
import { Button } from "../ui";

type Status = "open" | "resolved";

function AnswerForm({
  item,
  onDone,
  onCancel,
}: {
  item: UnansweredItem;
  onDone: (item: UnansweredItem) => void;
  onCancel: () => void;
}) {
  const toast = useToast();
  const [question, setQuestion] = useState(item.question);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      onDone(await api.answerToBase(item.id, question.trim(), answer.trim()));
      toast.ok("Ответ добавлен в базу — бот уже отвечает на такой вопрос");
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(false);
    }
  }

  const field =
    "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-sm outline-none placeholder:text-ink-3 focus:border-accent/50 focus:ring-4 focus:ring-accent/10";

  return (
    <form onSubmit={submit} className="mt-3 space-y-2.5 rounded-xl bg-sunken/60 p-3">
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-ink-2">Вопрос — как его задают клиенты</span>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={500}
          required
          className={`h-10 ${field}`}
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-ink-2">Ответ клиники</span>
        <textarea
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          maxLength={2000}
          rows={3}
          required
          autoFocus
          placeholder="Например: под общим наркозом не лечим, только под местной анестезией…"
          className={`min-h-20 resize-y ${field}`}
        />
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <p className="mr-auto text-[11px] leading-relaxed text-ink-3">
          Ответ попадёт в документ «Ответы администратора» — бот будет находить его, как любой документ базы.
        </p>
        <Button size="sm" onClick={onCancel} type="button">
          Отмена
        </Button>
        <Button
          size="sm"
          variant="primary"
          type="submit"
          loading={busy}
          disabled={question.trim().length < 3 || answer.trim().length < 3}
          icon={<BookPlus className="size-3.5" />}
        >
          Добавить в базу
        </Button>
      </div>
    </form>
  );
}

function ItemCard({ item, onChange }: { item: UnansweredItem; onChange: (item: UnansweredItem) => void }) {
  const toast = useToast();
  const [answering, setAnswering] = useState(false);
  const [busy, setBusy] = useState(false);

  async function toggle() {
    setBusy(true);
    try {
      onChange(await api.resolve(item.id, !item.resolved));
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rise rounded-2xl border border-line bg-surface p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-3">
        <span className="inline-flex items-center gap-1 font-medium text-ink-2">
          {item.channel === "telegram" ? (
            <Send className="size-3.5 text-[#229ED9]" />
          ) : (
            <MessageCircle className="size-3.5 text-accent" />
          )}
          {item.client}
        </span>
        <span>· {formatTime(item.created_at)}</span>
        <span>· {item.demo ? "пример" : item.channel === "telegram" ? "ваш диалог" : "ваш тестовый чат"}</span>
      </div>
      <p className="mt-2 text-[15px] leading-relaxed font-medium text-ink">«{item.question || "—"}»</p>
      <p className="mt-1 flex items-center gap-1.5 text-xs text-ink-3">
        <CircleHelp className="size-3.5" />
        {item.reason_label}
      </p>

      {item.kb_answer && (
        <div className="mt-3 rounded-xl border border-success/20 bg-success-soft px-3.5 py-2.5 text-sm">
          <p className="text-xs font-medium text-success">Ответ добавлен в базу знаний</p>
          <p className="mt-0.5 leading-relaxed text-ink">{item.kb_answer}</p>
        </div>
      )}

      {answering ? (
        <AnswerForm
          item={item}
          onCancel={() => setAnswering(false)}
          onDone={(next) => {
            setAnswering(false);
            onChange(next);
          }}
        />
      ) : (
        <div className="mt-3.5 flex flex-wrap items-center gap-2">
          {!item.resolved && (
            <Button
              size="sm"
              variant="primary"
              onClick={() => setAnswering(true)}
              icon={<BookPlus className="size-3.5" />}
            >
              Добавить ответ в базу
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            loading={busy}
            onClick={toggle}
            icon={item.resolved ? <RotateCcw className="size-3.5" /> : <Check className="size-3.5" />}
          >
            {item.resolved ? "Вернуть в нерешённые" : "Отметить решённым"}
          </Button>
          {item.channel === "telegram" && (
            <Link
              href={`/admin/dialogs?id=${item.conversation_id}`}
              className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-ink-2 hover:text-ink"
            >
              <MessageCircle className="size-3.5" />
              Диалог
            </Link>
          )}
        </div>
      )}
    </li>
  );
}

export function UnansweredView() {
  const { mutate: mutateAll } = useSWRConfig();
  const [status, setStatus] = useState<Status>("open");
  // Вопросы — порциями: докрутили до конца, просим ещё. Другая вкладка — с начала
  const [limit, setLimit] = useState(LIST_PAGE);
  const { data, mutate } = useSWR(["unanswered", status, limit], () => api.unanswered(status, limit), {
    refreshInterval: 8000,
    keepPreviousData: true,
  });
  const loadingMore = !!data?.has_more && data.items.length < limit;
  const more = useCallback(() => setLimit((l) => l + LIST_PAGE), []);

  function changed() {
    mutate();
    // Счётчик в меню и вторая вкладка тоже поменялись
    mutateAll((key) => Array.isArray(key) && key[0] === "unanswered");
    // Ответ в базу добавляет документ «Ответы администратора»
    mutateAll((key) => key === "documents" || (Array.isArray(key) && key[0] === "documents"));
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-5 sm:px-6 sm:py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Бот не смог ответить</h1>
      <p className="mt-1 max-w-2xl text-sm leading-relaxed text-ink-2">
        Вопросы клиентов, на которые в документах не нашлось ответа. По ним видно, чего не хватает в базе знаний.
        Добавьте ответ — и бот начнёт отвечать на такой вопрос сам.
      </p>

      <div className="mt-5 flex w-fit gap-1 rounded-xl bg-sunken p-1 text-xs font-medium" role="tablist">
        {(
          [
            ["open", "Нерешённые", data?.open],
            ["resolved", "Решённые", data?.resolved],
          ] as const
        ).map(([value, label, count]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={status === value}
            onClick={() => {
              setStatus(value);
              setLimit(LIST_PAGE);
            }}
            className={`h-7 rounded-lg px-3 transition-colors ${
              status === value ? "bg-surface text-ink shadow-sm" : "text-ink-2 hover:text-ink"
            }`}
          >
            {label}
            {!!count && <span className="ml-1 text-ink-3 tabular-nums">{count}</span>}
          </button>
        ))}
      </div>

      {!data ? (
        <div className="mt-4 space-y-3">
          {[0, 1].map((i) => (
            <div key={i} className="skeleton h-36 rounded-2xl" />
          ))}
        </div>
      ) : data.items.length === 0 ? (
        <p className="mt-10 text-center text-sm text-ink-3">
          {status === "open"
            ? "Все вопросы разобраны 👌 Спросите в тестовом чате о том, чего нет в документах, — вопрос появится здесь."
            : "Решённых вопросов пока нет."}
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {data.items.map((item) => (
            <ItemCard key={item.id} item={item} onChange={changed} />
          ))}
        </ul>
      )}
      <LoadMore hasMore={!!data?.has_more} loading={loadingMore} onMore={more} />
    </div>
  );
}
