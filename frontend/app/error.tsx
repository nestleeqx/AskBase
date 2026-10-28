"use client"; // Границы ошибок в Next.js — только клиентские компоненты

import { RotateCcw, TriangleAlert } from "lucide-react";
import { useEffect } from "react";
import { Button } from "@/components/ui";

/** Вместо стандартного «This page couldn't load» — понятное сообщение и кнопка «Обновить». */
export default function Error({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <div className="max-w-sm text-center">
        <span className="mx-auto grid size-11 place-items-center rounded-full bg-warn-soft text-warn">
          <TriangleAlert className="size-5" />
        </span>
        <h1 className="mt-4 text-lg font-semibold text-ink">Что-то пошло не так</h1>
        <p className="mt-1.5 text-sm text-ink-2">Обновите страницу — документы и настройки сохранены.</p>
        <div className="mt-5 flex justify-center gap-2">
          <Button variant="primary" icon={<RotateCcw className="size-4" />} onClick={() => retry()}>
            Попробовать снова
          </Button>
          <Button onClick={() => window.location.reload()}>Обновить страницу</Button>
        </div>
      </div>
    </div>
  );
}
