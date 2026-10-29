"use client";

import { ArrowRight, Eye, KeyRound, Lock } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import useSWR, { useSWRConfig } from "swr";
import { api, setOwnerToken } from "@/lib/api";
import { Logo } from "../Logo";
import { Button } from "../ui";

const GUEST = [
  "Диалоги клиентов с ботом и ответ администратора",
  "Тестовый чат: как бот ищет ответ в документах",
  "До 3 своих документов и свой Telegram-чат с ботом",
];

const OWNER = [
  "Документы и настройки бота — для всех клиентов",
  "Все диалоги и заявки, а не только демо",
  "Ответы администратора — в общую базу знаний",
];

export function LoginView() {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const { data: auth } = useSWR("auth", api.auth);

  // После смены роли сбрасываем кеш запросов: он собран от лица прежней роли
  async function enter() {
    await mutate(() => true, undefined, { revalidate: false });
    router.push("/admin/dialogs");
  }
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function login(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { token } = await api.login(password);
      setOwnerToken(token);
      await enter();
      // Next сохраняет страницу при переходе «назад» — без сброса кнопка так и крутилась бы
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function guest() {
    setOwnerToken(null);
    enter();
  }

  const ownerOff = auth && !auth.owner_enabled;

  return (
    <div className="relative flex min-h-full flex-col items-center justify-center px-4 py-10">
      <div className="dot-grid pointer-events-none absolute inset-0 -z-10" />
      <Link href="/" aria-label="AskBase — на главную">
        <Logo />
      </Link>
      <h1 className="mt-6 text-center text-2xl font-semibold tracking-tight text-balance">
        Вход в админку клиники «Белая линия»
      </h1>
      <p className="mt-2 max-w-md text-center text-sm leading-relaxed text-ink-2">
        Демо AskBase: бот отвечает клиентам стоматологии по её документам. Клиника, врачи и цены вымышлены.
      </p>

      <div className="mt-8 grid w-full max-w-3xl gap-4 md:grid-cols-2">
        <section className="rise flex flex-col rounded-3xl border border-accent/30 bg-surface p-6 shadow-[0_24px_50px_-30px_rgba(17,23,22,.45)]">
          <span className="grid size-11 place-items-center rounded-2xl bg-accent text-white">
            <Eye className="size-5" />
          </span>
          <h2 className="mt-4 text-lg font-semibold">Гость</h2>
          <p className="mt-1 text-sm text-ink-2">Без пароля — посмотреть и попробовать бота на своих данных.</p>
          <ul className="mt-4 space-y-2 text-sm text-ink-2">
            {GUEST.map((t) => (
              <li key={t} className="flex gap-2.5">
                <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-accent" />
                {t}
              </li>
            ))}
          </ul>
          <Button variant="primary" className="mt-6 h-11 w-full text-[15px]" onClick={guest}>
            Войти как гость
            <ArrowRight className="size-4" />
          </Button>
        </section>

        <section
          className="rise flex flex-col rounded-3xl border border-line bg-surface p-6"
          style={{ animationDelay: "80ms" }}
        >
          <span className="grid size-11 place-items-center rounded-2xl bg-sunken text-ink-2">
            <KeyRound className="size-5" />
          </span>
          <h2 className="mt-4 text-lg font-semibold">Владелец клиники</h2>
          <p className="mt-1 text-sm text-ink-2">Изменения действуют для всех клиентов бота.</p>
          <ul className="mt-4 space-y-2 text-sm text-ink-2">
            {OWNER.map((t) => (
              <li key={t} className="flex gap-2.5">
                <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-ink-3" />
                {t}
              </li>
            ))}
          </ul>
          <form onSubmit={login} className="mt-auto pt-6">
            <label className="relative block">
              <Lock className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-ink-3" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder={ownerOff ? "Вход владельца не настроен" : "Пароль владельца"}
                aria-label="Пароль владельца"
                disabled={!!ownerOff}
                className="h-11 w-full rounded-xl border border-line bg-surface pr-3 pl-10 text-sm outline-none placeholder:text-ink-3 focus:border-accent/50 focus:ring-4 focus:ring-accent/10 disabled:bg-sunken"
              />
            </label>
            {error && <p className="mt-2 text-sm text-danger">{error}</p>}
            <Button
              type="submit"
              className="mt-3 h-11 w-full text-[15px]"
              loading={busy}
              disabled={!password || !!ownerOff}
            >
              Войти как владелец
            </Button>
          </form>
        </section>
      </div>
    </div>
  );
}
