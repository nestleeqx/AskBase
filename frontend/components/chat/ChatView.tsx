"use client";

import { ChevronDown, MessageSquarePlus, SendHorizontal, Sparkles, UserRound } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { formatSeconds } from "@/lib/format";
import type { ChatMessage, Trace } from "@/lib/types";
import { DocIcon } from "../documents/DocIcon";
import { useToast } from "../Toast";
import { Button } from "../ui";

const STORAGE_KEY = "askbase:chat";

const GREETING =
  "Здравствуйте! Я бот клиники «Белая линия». Спросите про цены, врачей, подготовку к процедурам или запись — отвечу по документам клиники.";

const EXAMPLES = [
  "Сколько стоит удалить восьмёрку?",
  "Делаете виниры?",
  "Можно в рассрочку?",
  "Работаете в воскресенье?",
  "Сколько стоит ремонт машины?",
];

function readStored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function store(id: string | null) {
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {}
}

function TraceDetails({ trace, question }: { trace: Trace; question?: string }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="mt-2 rounded-xl border border-line bg-surface p-3 text-xs text-ink-2">
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

function BotBubble({ message, question }: { message: ChatMessage; question?: string }) {
  const [details, setDetails] = useState(false);
  const handoff = message.answered === false;
  return (
    <div className="rise flex max-w-[92%] flex-col items-start sm:max-w-[80%]">
      <div
        className={`rounded-2xl rounded-tl-md border px-4 py-3 text-sm leading-relaxed ${
          handoff ? "border-warn/25 bg-warn-soft" : "border-line bg-surface"
        }`}
      >
        {handoff && (
          <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-warn">
            <UserRound className="size-3.5" />
            Вопрос передан администратору
          </p>
        )}
        <p className="whitespace-pre-line text-ink">{message.text}</p>
        {message.sources.length > 0 && (
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5 border-t border-line pt-2.5">
            <span className="text-xs text-ink-3">{message.sources.length > 1 ? "Источники:" : "Источник:"}</span>
            {message.sources.map((s) => (
              <span
                key={s.id}
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
      {message.trace && (
        <div className="mt-1 w-full pl-1">
          <div className="flex flex-wrap items-center gap-x-2 text-xs text-ink-3">
            {message.latency_ms != null && <span>ответ за {formatSeconds(message.latency_ms)}</span>}
            {message.topic_label && <span>· {message.topic_label}</span>}
            <button
              type="button"
              onClick={() => setDetails((d) => !d)}
              className="inline-flex items-center gap-0.5 font-medium text-accent hover:underline"
            >
              · как бот искал ответ
              <ChevronDown className={`size-3.5 transition-transform ${details ? "rotate-180" : ""}`} />
            </button>
          </div>
          {details && <TraceDetails trace={message.trace} question={question} />}
        </div>
      )}
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="rise ml-auto max-w-[85%] rounded-2xl rounded-tr-md bg-accent px-4 py-2.5 text-sm leading-relaxed whitespace-pre-line text-white sm:max-w-[75%]">
      {text}
    </div>
  );
}

function Typing() {
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

export function ChatView() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loaded, setLoaded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  // Диалог продолжается после перезагрузки страницы
  useEffect(() => {
    const id = readStored();
    (id ? api.conversation(id) : Promise.resolve(null))
      .then((conv) => {
        if (!conv) return;
        setConversationId(conv.id);
        setMessages(conv.messages);
      })
      .catch(() => store(null))
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, pending]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || pending) return;
    setPending(question);
    setInput("");
    try {
      const reply = await api.ask(question, conversationId);
      setConversationId(reply.conversation_id);
      store(reply.conversation_id);
      setMessages((m) => [...m, reply.user, reply.bot]);
    } catch (e) {
      // Диалог могли удалить — начинаем новый и просим повторить
      if (e instanceof ApiError && e.status === 404) {
        setConversationId(null);
        store(null);
      }
      setInput(question);
      toast.error(e);
    } finally {
      setPending(null);
      inputRef.current?.focus();
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    send(input);
  }

  function reset() {
    setConversationId(null);
    setMessages([]);
    store(null);
    inputRef.current?.focus();
  }

  const empty = loaded && messages.length === 0 && !pending;

  return (
    <div className="mx-auto flex h-[calc(100dvh-4rem)] max-w-4xl flex-col px-4 py-5 sm:px-6 sm:py-6">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Тестовый чат</h1>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-ink-2">
            Тот же бот, что отвечает клиентам в Telegram. Под каждым ответом видно, какие фрагменты нашлись и какие
            вошли в ответ.
          </p>
        </div>
        <Button
          onClick={reset}
          disabled={!messages.length || !!pending}
          icon={<MessageSquarePlus className="size-4" />}
        >
          Новый диалог
        </Button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-line bg-sunken/50">
        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-3 py-4 scrollbar-thin sm:px-5">
          <div className="flex max-w-[92%] items-start gap-2.5 sm:max-w-[80%]">
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent text-white">
              <Sparkles className="size-4" />
            </span>
            <p className="rounded-2xl rounded-tl-md border border-line bg-surface px-4 py-3 text-sm leading-relaxed text-ink">
              {GREETING}
            </p>
          </div>
          {messages.map((m, i) =>
            m.role === "user" ? (
              <UserBubble key={m.id} text={m.text} />
            ) : (
              <BotBubble key={m.id} message={m} question={messages[i - 1]?.text} />
            ),
          )}
          {pending && (
            <>
              <UserBubble text={pending} />
              <Typing />
            </>
          )}
        </div>

        <div className="border-t border-line bg-surface p-3 sm:p-4">
          {empty && (
            <div className="mb-3 flex gap-1.5 overflow-x-auto pb-1 scrollbar-none">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => send(example)}
                  className="shrink-0 rounded-full border border-line bg-surface px-3 py-1 text-xs text-ink-2 transition-colors hover:border-accent/40 hover:bg-accent-soft hover:text-accent-ink"
                >
                  {example}
                </button>
              ))}
            </div>
          )}
          <form onSubmit={submit} className="flex gap-2">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              maxLength={500}
              placeholder="Напишите вопрос как клиент…"
              aria-label="Вопрос боту"
              className="h-11 min-w-0 flex-1 rounded-xl border border-line bg-surface px-3.5 text-sm outline-none placeholder:text-ink-3 focus:border-accent/40 focus:ring-4 focus:ring-accent-soft"
            />
            <Button
              type="submit"
              variant="primary"
              className="h-11 w-11 shrink-0 px-0 sm:w-auto sm:px-4"
              loading={!!pending}
              disabled={!input.trim()}
              aria-label="Отправить"
              icon={pending ? undefined : <SendHorizontal className="size-4" />}
            >
              <span className="max-sm:hidden">Отправить</span>
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
