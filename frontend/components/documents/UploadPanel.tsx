"use client";

import { Link2, Upload } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { formatNumber, plural } from "@/lib/format";
import type { UploadLimits } from "@/lib/types";
import { Button, Panel } from "../ui";

const ACCEPT = ".pdf,.docx,.txt";
const EXTENSIONS = ["pdf", "docx", "txt"];

type Props = {
  limits?: UploadLimits;
  busy: boolean;
  onFile: (file: File) => void;
  onUrl: (url: string) => Promise<boolean>;
  onReject: (message: string) => void;
};

/** Загрузка своего документа: файл перетаскиванием или кнопкой, либо ссылка на страницу сайта. */
export function UploadPanel({ limits, busy, onFile, onUrl, onReject }: Props) {
  const [tab, setTab] = useState<"file" | "url">("file");
  const [dragging, setDragging] = useState(false);
  const [url, setUrl] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const left = limits?.guest_docs_left ?? 0;
  // Владелец пополняет общую базу клиники — гостевой лимит к нему не относится
  const full = !!limits && !limits.owner && left === 0;
  const disabled = busy || full || !limits;

  function pick(file: File | undefined) {
    if (!file || !limits) return;
    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (ext === "doc") return onReject("Старый формат .doc не поддерживается. Сохраните файл в Word как DOCX.");
    if (!EXTENSIONS.includes(ext)) return onReject("Поддерживаются файлы PDF, DOCX и TXT.");
    if (file.size > limits.max_upload_mb * 1024 * 1024)
      return onReject(`Файл больше ${limits.max_upload_mb} МБ — для демо это слишком много.`);
    onFile(file);
  }

  async function submitUrl(e: FormEvent) {
    e.preventDefault();
    if (url.trim() && (await onUrl(url.trim()))) setUrl("");
  }

  return (
    <Panel className="p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">Добавить свой документ</h2>
          <p className="mt-1 text-sm text-ink-2">Проверьте бота на своих данных: прайсе, FAQ или странице сайта.</p>
        </div>
        <div className="flex rounded-xl bg-sunken p-1 text-sm" role="tablist">
          {(
            [
              ["file", "Файл", Upload],
              ["url", "Ссылка", Link2],
            ] as const
          ).map(([key, label, Icon]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={`flex h-8 items-center gap-1.5 rounded-lg px-3 font-medium transition-colors ${
                tab === key ? "bg-surface text-ink shadow-sm" : "text-ink-2 hover:text-ink"
              }`}
            >
              <Icon className="size-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {tab === "file" ? (
        <button
          type="button"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            if (!disabled) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (!disabled) pick(e.dataTransfer.files[0]);
          }}
          className={`mt-4 flex w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed px-4 py-7 text-center transition-colors disabled:cursor-not-allowed disabled:opacity-55 ${
            dragging
              ? "border-accent bg-accent-soft/50"
              : "border-line-strong hover:border-accent/50 hover:bg-accent-soft/30"
          }`}
        >
          <span className="grid size-11 place-items-center rounded-full bg-accent-soft text-accent">
            <Upload className="size-5" />
          </span>
          <span className="mt-3 text-sm font-medium text-ink">
            Перетащите файл сюда или{" "}
            <span className="font-medium text-accent underline underline-offset-4">выберите на компьютере</span>
          </span>
          <span className="mt-1 text-xs text-ink-3">
            {limits
              ? `PDF, DOCX или TXT до ${String(limits.max_upload_mb).replace(".", ",")} МБ, PDF — до ${limits.max_pdf_pages} страниц`
              : "PDF, DOCX или TXT"}
          </span>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => {
              pick(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </button>
      ) : (
        <form onSubmit={submitUrl} className="mt-4 flex flex-col gap-2 sm:flex-row">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={disabled}
            inputMode="url"
            placeholder="https://сайт-клиники.ru/ceny"
            aria-label="Ссылка на страницу сайта"
            className="h-10 w-full min-w-0 rounded-xl border border-line bg-surface px-3 text-sm outline-none sm:flex-1 placeholder:text-ink-3 focus:border-accent/50 focus:ring-4 focus:ring-accent/10 disabled:opacity-55"
          />
          <Button type="submit" variant="primary" className="h-10" loading={busy} disabled={disabled || !url.trim()}>
            Загрузить страницу
          </Button>
        </form>
      )}

      <p className="mt-3 text-xs leading-relaxed text-ink-3">
        {limits &&
          (limits.owner
            ? `Документ попадёт в общую базу клиники: по нему бот будет отвечать всем клиентам. Объём — до ${formatNumber(limits.max_doc_chars)} символов.`
            : full
              ? `Вы загрузили ${limits.guest_docs_limit} ${plural(limits.guest_docs_limit, ["документ", "документа", "документов"])} — это максимум для демо. Удалите один, чтобы добавить новый.`
              : `Можно добавить ещё ${left} ${plural(left, ["документ", "документа", "документов"])}. Их видите только вы, через ${limits.guest_docs_ttl_hours} ${plural(limits.guest_docs_ttl_hours, ["час", "часа", "часов"])} они удалятся. Объём — до ${formatNumber(limits.max_doc_chars)} символов.`)}
      </p>
    </Panel>
  );
}
