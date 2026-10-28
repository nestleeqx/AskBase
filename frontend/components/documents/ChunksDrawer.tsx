"use client";

import { X } from "lucide-react";
import { useEffect } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { formatNumber, KIND_LABELS, plural } from "@/lib/format";
import { DocIcon } from "./DocIcon";

/** Боковая панель: на какие фрагменты разрезан документ — то, что видит поиск. */
export function ChunksDrawer({ docId, onClose }: { docId: string; onClose: () => void }) {
  const { data, error } = useSWR(["chunks", docId], () => api.chunks(docId));

  useEffect(() => {
    const root = document.documentElement;
    const overflow = root.style.overflow;
    root.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      root.style.overflow = overflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const doc = data?.document;

  return (
    <div className="fixed inset-0 z-50">
      <div className="fade-in absolute inset-0 bg-ink/30" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Фрагменты документа"
        className="slide-from-right absolute inset-y-0 right-0 flex w-full max-w-xl flex-col bg-surface shadow-xl"
      >
        <header className="flex items-start gap-3 border-b border-line px-5 py-4">
          {doc ? <DocIcon kind={doc.kind} /> : <span className="skeleton size-10 rounded-xl" />}
          <div className="min-w-0 flex-1">
            {doc ? (
              <>
                <h2 className="font-semibold text-balance">{doc.title}</h2>
                <p className="mt-0.5 text-sm text-ink-2">
                  {KIND_LABELS[doc.kind]} · {doc.chunks_count}{" "}
                  {plural(doc.chunks_count, ["фрагмент", "фрагмента", "фрагментов"])}
                </p>
              </>
            ) : (
              <span className="skeleton block h-5 w-48 rounded" />
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="grid size-9 shrink-0 place-items-center rounded-lg text-ink-2 hover:bg-sunken"
          >
            <X className="size-4.5" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4 scrollbar-thin">
          <p className="mb-4 text-sm leading-relaxed text-ink-2">
            Документ разрезан на фрагменты до 800 символов. На вопрос клиента поиск находит несколько самых подходящих
            фрагментов, и нейросеть отвечает только по ним.
          </p>
          {error && <p className="text-sm text-danger">{error.message}</p>}
          {!data && !error && (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-28 rounded-xl" />
              ))}
            </div>
          )}
          <ol className="space-y-3">
            {data?.chunks.map((chunk) => (
              <li key={chunk.id} className="rounded-xl border border-line p-3.5">
                <p className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-3">
                  <span className="rounded-md bg-sunken px-1.5 py-0.5 font-semibold text-ink-2 tabular-nums">
                    {chunk.position + 1}
                  </span>
                  {chunk.heading && <span className="font-medium text-ink-2">{chunk.heading}</span>}
                  <span className="ml-auto tabular-nums">{formatNumber(chunk.text.length)} симв.</span>
                </p>
                <p className="text-sm leading-relaxed whitespace-pre-line text-ink">{chunk.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </aside>
    </div>
  );
}
