"use client";

import { AlertTriangle } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Button } from "./ui";

type ConfirmOptions = {
  title: string;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** danger — необратимое действие: красная кнопка и предупреждающий значок */
  tone?: "default" | "danger";
};

type Pending = ConfirmOptions & { resolve: (ok: boolean) => void };

const ConfirmContext = createContext<(options: ConfirmOptions) => Promise<boolean>>(async () => false);

/** Замена window.confirm: `if (!(await confirm({ title: "…" }))) return;` */
export function useConfirm() {
  return useContext(ConfirmContext);
}

function Dialog({ pending, onClose }: { pending: Pending; onClose: (ok: boolean) => void }) {
  const titleId = useId();
  const descId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const danger = pending.tone === "danger";

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    // Для необратимых действий фокус на «Отмене», чтобы случайный Enter ничего не удалил
    (danger ? cancelRef : confirmRef).current?.focus();

    const root = document.documentElement;
    const overflow = root.style.overflow;
    root.style.overflow = "hidden";

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose(false);
      }
      // Фокус не уходит из окна: Tab переключает только две кнопки
      if (e.key === "Tab") {
        const buttons = [cancelRef.current, confirmRef.current].filter(Boolean) as HTMLElement[];
        const index = buttons.indexOf(document.activeElement as HTMLElement);
        e.preventDefault();
        buttons[(index + (e.shiftKey ? -1 : 1) + buttons.length) % buttons.length]?.focus();
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      root.style.overflow = overflow;
      previous?.focus?.();
    };
  }, [danger, onClose]);

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center p-4 sm:items-center">
      <div className="fade-in absolute inset-0 bg-ink/30 backdrop-blur-[2px]" onClick={() => onClose(false)} />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={pending.description ? descId : undefined}
        className="pop relative w-full max-w-sm rounded-3xl border border-line bg-surface p-6 shadow-[0_30px_60px_-20px_rgba(21,23,28,.35)]"
      >
        <div className="flex gap-3">
          {danger && (
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-danger-soft text-danger">
              <AlertTriangle className="size-4.5" />
            </span>
          )}
          <div className="min-w-0">
            <h2 id={titleId} className="font-semibold text-balance">
              {pending.title}
            </h2>
            {pending.description && (
              <div id={descId} className="mt-1.5 text-sm leading-relaxed text-ink-2">
                {pending.description}
              </div>
            )}
          </div>
        </div>
        <div className="mt-5 flex gap-2 sm:justify-end">
          <Button ref={cancelRef} variant="secondary" className="max-sm:flex-1" onClick={() => onClose(false)}>
            {pending.cancelLabel ?? "Отмена"}
          </Button>
          <Button
            ref={confirmRef}
            variant={danger ? "destructive" : "primary"}
            className="max-sm:flex-1"
            onClick={() => onClose(true)}
          >
            {pending.confirmLabel ?? "Подтвердить"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);

  const confirm = useCallback(
    (options: ConfirmOptions) => new Promise<boolean>((resolve) => setPending({ ...options, resolve })),
    [],
  );

  const close = useCallback(
    (ok: boolean) => {
      pending?.resolve(ok);
      setPending(null);
    },
    [pending],
  );

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending && <Dialog pending={pending} onClose={close} />}
    </ConfirmContext.Provider>
  );
}
