"use client";

import { MessageSquarePlus, SendHorizontal, Sparkles } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import useSWR from "swr";
import { api, ApiError } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";
import { useToast } from "../Toast";
import { Button } from "../ui";
import { BotBubble, Typing, UserBubble } from "./Bubbles";

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

export function ChatView() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loaded, setLoaded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const toast = useToast();
  // Приветствие — из настроек бота: гость может поменять его на странице «Настройки бота»
  const { data: settings } = useSWR("settings", api.settings);

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
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-[#5eead4] to-[#0d9488] text-white">
              <Sparkles className="size-4" />
            </span>
            <p className="rounded-2xl rounded-tl-md border border-line bg-surface px-4 py-3 text-sm leading-relaxed whitespace-pre-line text-ink">
              {settings?.greeting ?? GREETING}
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
                  className="shrink-0 rounded-full border border-line bg-surface px-3 py-1 text-xs text-ink-2 transition-colors hover:border-accent/40 hover:bg-accent-soft/50 hover:text-accent-ink"
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
              placeholder="Ваш вопрос боту…"
              aria-label="Вопрос боту"
              className="h-11 min-w-0 flex-1 rounded-xl border border-line bg-surface px-3.5 text-sm outline-none placeholder:text-ink-3 focus:border-accent/50 focus:ring-4 focus:ring-accent/10"
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
