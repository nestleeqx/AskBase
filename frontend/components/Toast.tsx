"use client";

import { BellRing, CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

// info — событие от клиента (позвал администратора, новая заявка): со ссылкой и держится дольше
type Toast = { id: number; kind: "ok" | "error" | "info"; text: string; href?: string };

const ToastContext = createContext<(kind: Toast["kind"], text: string, href?: string) => void>(() => {});

const ICONS = {
  ok: <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />,
  error: <XCircle className="mt-0.5 size-4 shrink-0 text-danger" />,
  info: <BellRing className="mt-0.5 size-4 shrink-0 text-accent" />,
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const push = useCallback((kind: Toast["kind"], text: string, href?: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, text, href }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "info" ? 9000 : 4500);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-4 bottom-4 z-[60] flex flex-col gap-2 sm:inset-x-auto sm:right-4 sm:w-full sm:max-w-sm">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === "info" ? "status" : undefined}
            className="pop pointer-events-auto flex items-start gap-2.5 rounded-2xl border border-line bg-surface px-4 py-3 text-sm text-ink shadow-[0_18px_40px_-16px_rgba(21,23,28,.35)]"
          >
            {ICONS[t.kind]}
            <span className="flex-1">{t.text}</span>
            {t.href && (
              <Link
                href={t.href}
                // Перешли по уведомлению — оно своё дело сделало, закрываем сразу
                onClick={() => setToasts((all) => all.filter((x) => x.id !== t.id))}
                className="shrink-0 font-medium text-accent hover:underline"
              >
                Открыть
              </Link>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const push = useContext(ToastContext);
  return {
    ok: (text: string) => push("ok", text),
    error: (e: unknown) => push("error", e instanceof Error ? e.message : String(e)),
    info: (text: string, href?: string) => push("info", text, href),
  };
}
