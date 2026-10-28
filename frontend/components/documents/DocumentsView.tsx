"use client";

import { AlertCircle, CheckCircle2, Download, ExternalLink, Layers, Loader2, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { formatNumber, formatSeconds, formatSize, KIND_LABELS, plural } from "@/lib/format";
import type { Doc } from "@/lib/types";
import { useConfirm } from "../Confirm";
import { ScopeNote } from "../ScopeNote";
import { useToast } from "../Toast";
import { buttonClasses, Panel, SectionLabel } from "../ui";
import { ChunksDrawer } from "./ChunksDrawer";
import { DocIcon } from "./DocIcon";
import { UploadPanel } from "./UploadPanel";

type Pending = { key: string; name: string };

function meta(doc: Doc) {
  const parts: string[] = [KIND_LABELS[doc.kind]];
  if (doc.pages) parts.push(`${doc.pages} ${plural(doc.pages, ["страница", "страницы", "страниц"])}`);
  if (doc.status === "ready") {
    parts.push(`${formatNumber(doc.chars)} ${plural(doc.chars, ["символ", "символа", "символов"])}`);
  } else if (doc.size_bytes) {
    parts.push(formatSize(doc.size_bytes));
  }
  return parts.join(" · ");
}

function Status({ doc }: { doc: Doc }) {
  if (doc.status === "indexing")
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-sunken px-2 py-0.5 text-xs font-medium text-ink-2">
        <Loader2 className="size-3 animate-spin" />
        Индексируется
      </span>
    );
  if (doc.status === "error")
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-danger-soft px-2 py-0.5 text-xs font-medium text-danger">
        <AlertCircle className="size-3" />
        Не обработан
      </span>
    );
  return (
    <span
      className="inline-flex items-center gap-1 rounded-md bg-success-soft px-2 py-0.5 text-xs font-medium whitespace-nowrap text-success"
      title="Бот уже отвечает по этому документу"
    >
      <CheckCircle2 className="size-3" />
      Готов{doc.index_ms != null && ` · за ${formatSeconds(doc.index_ms)}`}
    </span>
  );
}

function DocRow({
  doc,
  fresh,
  onOpen,
  onDelete,
}: {
  doc: Doc;
  fresh: boolean;
  onOpen: () => void;
  onDelete: () => void;
}) {
  const ready = doc.status === "ready";
  const icon = "size-4";
  return (
    <li
      className={`flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:px-5 ${fresh ? "rise bg-accent-soft/40" : ""}`}
    >
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <DocIcon kind={doc.kind} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {ready ? (
              <button type="button" onClick={onOpen} className="text-left font-medium text-ink hover:text-accent">
                {doc.title}
              </button>
            ) : (
              <span className="font-medium text-ink">{doc.title}</span>
            )}
            <Status doc={doc} />
          </div>
          <p className="mt-0.5 text-sm text-ink-3">{meta(doc)}</p>
          {doc.error && <p className="mt-1 text-sm text-danger">{doc.error}</p>}
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-1.5 pl-[52px] sm:pl-0">
        {ready && (
          <button type="button" onClick={onOpen} className={buttonClasses("secondary", "sm")}>
            <Layers className={icon} />
            {doc.chunks_count} {plural(doc.chunks_count, ["фрагмент", "фрагмента", "фрагментов"])}
          </button>
        )}
        {doc.downloadable && (
          <a href={api.fileUrl(doc.id)} target="_blank" rel="noreferrer" className={buttonClasses("ghost", "sm")}>
            <Download className={icon} />
            Оригинал
          </a>
        )}
        {doc.kind === "url" && doc.source_url && (
          <a href={doc.source_url} target="_blank" rel="noreferrer" className={buttonClasses("ghost", "sm")}>
            <ExternalLink className={icon} />
            Страница
          </a>
        )}
        {doc.own && (
          <button
            type="button"
            onClick={onDelete}
            aria-label={`Удалить «${doc.title}»`}
            title="Удалить"
            className={`${buttonClasses("ghost", "sm")} hover:text-danger`}
          >
            <Trash2 className={icon} />
          </button>
        )}
      </div>
    </li>
  );
}

function PendingRow({ name }: { name: string }) {
  return (
    <li className="rise flex items-center gap-3 px-4 py-3.5 sm:px-5">
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent">
        <Loader2 className="size-4.5 animate-spin" />
      </span>
      <div className="min-w-0">
        <p className="truncate font-medium text-ink">{name}</p>
        <p className="text-sm text-ink-3">Читаем, режем на фрагменты и индексируем…</p>
      </div>
    </li>
  );
}

function ListSkeleton() {
  return (
    <ul className="divide-y divide-line">
      {[0, 1, 2, 3].map((i) => (
        <li key={i} className="flex items-center gap-3 px-5 py-4">
          <span className="skeleton size-10 rounded-xl" />
          <span className="flex-1 space-y-2">
            <span className="skeleton block h-4 w-48 rounded" />
            <span className="skeleton block h-3 w-32 rounded" />
          </span>
        </li>
      ))}
    </ul>
  );
}

export function DocumentsView() {
  const { data, error, mutate } = useSWR("documents", api.documents, {
    // Пока что-то индексируется — опрашиваем, потом перестаём
    refreshInterval: (latest) => (latest?.documents.some((d) => d.status === "indexing") ? 2000 : 0),
  });
  const [pending, setPending] = useState<Pending[]>([]);
  const [fresh, setFresh] = useState<string | null>(null);
  const [opened, setOpened] = useState<string | null>(null);
  const toast = useToast();
  const confirm = useConfirm();
  const closeDrawer = useCallback(() => setOpened(null), []);

  async function track(name: string, upload: () => Promise<Doc>): Promise<boolean> {
    const key = crypto.randomUUID();
    setPending((p) => [{ key, name }, ...p]);
    try {
      const doc = await upload();
      await mutate();
      setFresh(doc.id);
      if (doc.status === "ready") {
        toast.ok(`«${doc.title}» готов за ${formatSeconds(doc.index_ms ?? 0)} — по нему уже можно искать.`);
        return true;
      }
      toast.error(doc.error ?? "Не удалось обработать документ.");
    } catch (e) {
      toast.error(e);
    } finally {
      setPending((p) => p.filter((x) => x.key !== key));
    }
    return false;
  }

  async function remove(doc: Doc) {
    const ok = await confirm({
      title: `Удалить «${doc.title}»?`,
      description: "Документ и его фрагменты исчезнут из поиска.",
      confirmLabel: "Удалить",
      tone: "danger",
    });
    if (!ok) return;
    try {
      await api.deleteDocument(doc.id);
      await mutate();
      toast.ok("Документ удалён.");
    } catch (e) {
      toast.error(e);
    }
  }

  const docs = data?.documents ?? [];
  const own = docs.filter((d) => d.own);
  const base = docs.filter((d) => !d.own);
  const chunks = docs.filter((d) => d.status === "ready").reduce((sum, d) => sum + d.chunks_count, 0);

  const rows = (list: Doc[]) =>
    list.map((doc) => (
      <DocRow
        key={doc.id}
        doc={doc}
        fresh={doc.id === fresh}
        onOpen={() => setOpened(doc.id)}
        onDelete={() => remove(doc)}
      />
    ));

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Документы</h1>
        <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-ink-2">
          База знаний, по которой бот отвечает клиентам. Новый документ становится доступен боту сразу после индексации
          — обычно за несколько секунд.
        </p>
        {data && (
          <ScopeNote
            owner={data.limits.owner}
            guest="Это демо-песочница: ваши документы бот использует только в вашем тестовом чате и в вашем Telegram-чате, подключённом к админке. Для остальных клиентов база клиники не меняется, а ваши документы удалятся через сутки."
            clinic="Вы вошли как владелец: загруженный документ попадает в общую базу клиники, и бот отвечает по нему всем клиентам."
          />
        )}
      </div>

      <UploadPanel
        limits={data?.limits}
        busy={pending.length > 0}
        onFile={(file) => track(file.name, () => api.uploadFile(file))}
        onUrl={(url) => track(url, () => api.uploadUrl(url))}
        onReject={(message) => toast.error(message)}
      />

      {error && <Panel className="mt-6 p-5 text-sm text-danger">{error.message}</Panel>}

      {(own.length > 0 || pending.length > 0) && (
        <section className="mt-8">
          <SectionLabel className="mb-2 px-1">Ваши документы — видны только вам</SectionLabel>
          <Panel className="overflow-hidden">
            <ul className="divide-y divide-line">
              {pending.map((p) => (
                <PendingRow key={p.key} name={p.name} />
              ))}
              {rows(own)}
            </ul>
          </Panel>
        </section>
      )}

      <section className="mt-8">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-1">
          <SectionLabel className="">Документы клиники</SectionLabel>
          {data && (
            <span className="text-xs text-ink-3">
              Всего в базе: {docs.length} {plural(docs.length, ["документ", "документа", "документов"])}, {chunks}{" "}
              {plural(chunks, ["фрагмент", "фрагмента", "фрагментов"])}
            </span>
          )}
        </div>
        <Panel className="overflow-hidden">
          {data ? <ul className="divide-y divide-line">{rows(base)}</ul> : <ListSkeleton />}
        </Panel>
      </section>

      {opened && <ChunksDrawer docId={opened} onClose={closeDrawer} />}
    </div>
  );
}
