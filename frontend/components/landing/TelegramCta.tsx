"use client";

import { Send } from "lucide-react";
import useSWR from "swr";
import { api } from "@/lib/api";

/** Ссылка на бота в Telegram. Если бот выключен на сервере, кнопки нет. */
export function TelegramCta({ className }: { className: string }) {
  const { data } = useSWR("telegram", api.telegram);
  if (!data?.enabled || !data.username) return null;
  return (
    <a href={`https://t.me/${data.username}`} target="_blank" rel="noreferrer" className={className}>
      <Send className="size-4 text-[#229ED9]" />
      Написать боту в Telegram
    </a>
  );
}
