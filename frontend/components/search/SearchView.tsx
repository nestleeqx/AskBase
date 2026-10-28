"use client";

import { ArrowRight, Search, Sparkles, Type } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { api } from "@/lib/api";
import { formatSeconds, plural } from "@/lib/format";
import type { SearchHit, SearchResult } from "@/lib/types";
import { DocIcon } from "../documents/DocIcon";
import { useToast } from "../Toast";
import { Button, Panel } from "../ui";

const EXAMPLES = [
  "Сколько стоит удалить восьмёрку?",
  "Кто у вас ставит импланты?",
  "Можно оплатить в рассрочку?",
  "Что взять с собой, если веду ребёнка?",
  "Вы работаете в воскресенье?",
  "сколько стоят брэкеты",
];

// Служебные слова вопроса не подсвечиваем: они есть почти в любом тексте
const STOP = new Set([
  "сколько",
  "стоит",
  "стоят",
  "можно",
  "есть",
  "как",
  "что",
  "кто",
  "где",
  "когда",
  "вас",
  "вы",
  "это",
  "ли",
  "или",
  "если",
  "надо",
  "нужно",
]);

/** Подсветка слов вопроса во фрагменте: по началу слова, чтобы «удалить» нашло «удаление». */
function highlight(text: string, question: string): ReactNode {
  const stems = question
    .toLowerCase()
    .match(/[\p{L}\d]+/gu)
    ?.filter((w) => w.length >= 3 && !STOP.has(w))
    .map((w) => (w.length > 5 ? w.slice(0, Math.max(4, w.length - 3)) : w))
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!stems?.length) return text;
  const re = new RegExp(`(?<![\\p{L}\\d])((?:${stems.join("|")})[\\p{L}\\d]*)`, "giu");
  return text.split(re).map((part, i) =>
    i % 2 ? (
      <mark key={i} className="hl">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

function place(n: number) {
  return `${n}-е место`;
}

function HitCard({ hit, question }: { hit: SearchHit; question: string }) {
  const percent = Math.max(0, Math.min(1, hit.similarity)) * 100;
  return (
    <li
      className="rise rounded-2xl border border-line bg-surface p-4 sm:p-5"
      style={{ animationDelay: `${hit.rank * 40}ms` }}
    >
      <div className="flex items-start gap-3">
        <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-ink text-xs font-semibold text-white tabular-nums">
          {hit.rank}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <DocIcon kind={hit.document.kind} size="sm" />
            <span className="font-medium text-ink">{hit.document.title}</span>
            {hit.chunk.heading && <span className="text-sm text-ink-3">· {hit.chunk.heading}</span>}
            {hit.document.own && (
              <span className="rounded-md bg-accent-soft px-1.5 py-px text-[11px] font-medium text-accent-ink">
                ваш документ
              </span>
            )}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
            <div
              className="flex min-w-[180px] flex-1 items-center gap-2.5"
              title="Насколько фрагмент близок к вопросу по смыслу"
            >
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-sunken">
                <span className="grow block h-full rounded-full bg-accent" style={{ width: `${percent}%` }} />
              </span>
              <span className="text-xs whitespace-nowrap text-ink-2 tabular-nums">
                близость{" "}
                {hit.similarity.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {hit.vector_rank && (
                <span
                  className="inline-flex items-center gap-1 rounded-md bg-accent-soft px-1.5 py-0.5 text-[11px] font-medium text-accent-ink"
                  title={`В поиске по смыслу — ${place(hit.vector_rank)}`}
                >
                  <Sparkles className="size-3" />
                  по смыслу · {hit.vector_rank}
                </span>
              )}
              {hit.keyword_rank && (
                <span
                  className="inline-flex items-center gap-1 rounded-md bg-info-soft px-1.5 py-0.5 text-[11px] font-medium text-info"
                  title={`В поиске по словам — ${place(hit.keyword_rank)}`}
                >
                  <Type className="size-3" />
                  по словам · {hit.keyword_rank}
                </span>
              )}
            </div>
          </div>

          <p className="mt-3 rounded-xl bg-sunken/70 p-3 text-sm leading-relaxed whitespace-pre-line text-ink">
            {highlight(hit.chunk.text, question)}
          </p>
        </div>
      </div>
    </li>
  );
}

function Intro() {
  return (
    <Panel className="mt-6 p-5 sm:p-6">
      <h2 className="font-semibold">Как бот ищет ответ</h2>
      <ol className="mt-3 grid gap-3 text-sm text-ink-2 sm:grid-cols-3">
        {[
          ["Ищет по смыслу", "«чистка зубов» найдёт «профессиональную гигиену», даже если слов нет в вопросе."],
          ["Ищет по словам", "Фамилии врачей, названия процедур и цифры находятся точно."],
          ["Берёт лучшие 6", "Два списка объединяются, и нейросеть отвечает только по этим фрагментам."],
        ].map(([title, text], i) => (
          <li key={title} className="rounded-xl bg-sunken/70 p-3.5">
            <span className="text-xs font-semibold text-accent">Шаг {i + 1}</span>
            <p className="mt-1 font-medium text-ink">{title}</p>
            <p className="mt-1 leading-relaxed">{text}</p>
          </li>
        ))}
      </ol>
    </Panel>
  );
}

export function SearchView() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const toast = useToast();

  async function run(q: string) {
    const text = q.trim();
    if (!text) return;
    setQuestion(text);
    setLoading(true);
    try {
      setResult(await api.search(text));
    } catch (e) {
      toast.error(e);
    } finally {
      setLoading(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    run(question);
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Проверка поиска</h1>
        <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-ink-2">
          Задайте вопрос так, как его написал бы клиент, и посмотрите, какие фрагменты базы найдутся. Именно их
          нейросеть получит перед ответом.
        </p>
      </div>

      <Panel className="p-4 sm:p-5">
        <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              maxLength={500}
              placeholder="Например: сколько стоит чистка зубов?"
              aria-label="Вопрос клиента"
              className="h-11 w-full rounded-xl border border-line bg-surface pr-3 pl-9 text-sm outline-none placeholder:text-ink-3 focus:border-accent/40 focus:ring-4 focus:ring-accent-soft"
            />
          </div>
          <Button type="submit" variant="primary" className="h-11 px-5" loading={loading} disabled={!question.trim()}>
            Найти
          </Button>
        </form>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => run(example)}
              disabled={loading}
              className="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-3 py-1 text-xs text-ink-2 transition-colors hover:border-accent/40 hover:bg-accent-soft hover:text-accent-ink disabled:opacity-50"
            >
              {example}
              <ArrowRight className="size-3" />
            </button>
          ))}
        </div>
      </Panel>

      {!result && !loading && <Intro />}

      {loading && !result && (
        <div className="mt-6 space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-36 rounded-2xl" />
          ))}
        </div>
      )}

      {result && (
        <section className={`mt-6 transition-opacity ${loading ? "opacity-50" : ""}`} aria-live="polite">
          <p className="mb-3 px-1 text-sm text-ink-2">
            {result.results.length
              ? `${result.results.length} ${plural(result.results.length, ["фрагмент", "фрагмента", "фрагментов"])} по вопросу «${result.question}» · поиск занял ${formatSeconds(result.took_ms)}`
              : `По вопросу «${result.question}» ничего не нашлось.`}
          </p>
          <ol className="space-y-3" key={result.question + result.took_ms}>
            {result.results.map((hit) => (
              <HitCard key={hit.chunk.id} hit={hit} question={result.question} />
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
