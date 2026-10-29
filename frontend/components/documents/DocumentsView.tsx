"use client";

import { AlertCircle, CheckCircle2, Download, ExternalLink, Layers, Loader2, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { formatNumber, formatSeconds, formatSize, KIND_LABELS, plural } from "@/lib/format";
import { revealOnMobile } from "@/lib/reveal";
import type { Doc } from "@/lib/types";
import { useConfirm } from "../Confirm";
import { ScopeNote } from "../ScopeNote";
import { useToast } from "../Toast";
import { LIST_PAGE, LoadMore } from "../LoadMore";
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
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-sunken text-ink">
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
  // Длинный список — порциями: докрутили до конца, просим ещё LIST_PAGE
  const [limit, setLimit] = useState(LIST_PAGE);
  const { mutate: mutateAll } = useSWRConfig();
  const { data, error } = useSWR(["documents", limit], () => api.documents(limit), {
    keepPreviousData: true,
    // Пока что-то индексируется — опрашиваем, потом перестаём
    refreshInterval: (latest) => (latest?.documents.some((d) => d.status === "indexing") ? 2000 : 0),
  });
  const [pending, setPending] = useState<Pending[]>([]);
  const [fresh, setFresh] = useState<string | null>(null);
  const [opened, setOpened] = useState<string | null>(null);
  const toast = useToast();
  const confirm = useConfirm();
  const closeDrawer = useCallback(() => setOpened(null), []);
  const uploadsRef = useRef<HTMLElement>(null);
  const uploading = pending.length > 0;

  // Загрузка началась — на телефоне показываем строку с прогрессом, а не форму загрузки
  useEffect(() => {
    if (uploading) revealOnMobile(uploadsRef.current);
  }, [uploading]);

  async function track(name: string, upload: () => Promise<Doc>): Promise<boolean> {
    const key = crypto.randomUUID();
    setPending((p) => [{ key, name }, ...p]);
    try {
      const doc = await upload();
      await refresh();
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
      await refresh();
      toast.ok("Документ удалён.");
    } catch (e) {
      toast.error(e);
    }
  }

  const docs = data?.documents ?? [];
  const own = docs.filter((d) => d.own);
  const base = docs.filter((d) => !d.own);
  const loadingMore = !!data?.has_more && docs.length < limit;
  const more = useCallback(() => setLimit((l) => l + LIST_PAGE), []);
  // После загрузки или удаления обновляем и список, и счётчик документов в меню
  const refresh = () => mutateAll((key) => key === "documents" || (Array.isArray(key) && key[0] === "documents"));

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
        <section ref={uploadsRef} className="mt-8 scroll-mt-20">
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
              Всего в базе: {data.total} {plural(data.total, ["документ", "документа", "документов"])},{" "}
              {data.chunks_total} {plural(data.chunks_total, ["фрагмент", "фрагмента", "фрагментов"])}
            </span>
          )}
        </div>
        <Panel className="overflow-hidden">
          {data ? <ul className="divide-y divide-line">{rows(base)}</ul> : <ListSkeleton />}
        </Panel>
        <LoadMore hasMore={!!data?.has_more} loading={loadingMore} onMore={more} />
      </section>

      {opened && <ChunksDrawer docId={opened} onClose={closeDrawer} />}
    </div>
  );
}
