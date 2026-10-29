"use client";

import { CalendarCheck, Check, Headset, UserRound } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

// meta — главное, видно всегда; more — подробность, на телефоне прячется, чтобы строка влезла
type Event = { id: string; avatar: ReactNode; color: string; title: ReactNode; meta: ReactNode; more: string };

const letter = (l: string) => <span className="text-sm font-semibold text-white">{l}</span>;

// События из демо-диалогов клиники — как лента в админке. Идут по кругу
const EVENTS: Event[] = [
  {
    id: "anna",
    avatar: letter("А"),
    color: "#0891b2",
    title: (
      <>
        <b className="font-semibold">Анна</b>: «Сколько стоит удалить зуб мудрости?»
      </>
    ),
    meta: (
      <>
        <Check className="size-3.5 shrink-0 text-accent" />
        Бот ответил за 2,1 с
      </>
    ),
    more: "Источник: Прайс-лист",
  },
  {
    id: "olga",
    avatar: letter("О"),
    color: "#6d4ae0",
    title: (
      <>
        <b className="font-semibold">Ольга</b> записалась на приём
      </>
    ),
    meta: (
      <>
        <CalendarCheck className="size-3.5 shrink-0 text-success" />
        Заявка в админке
      </>
    ),
    more: "в субботу утром",
  },
  {
    id: "pavel",
    avatar: <UserRound className="size-4 text-ink-2" />,
    color: "var(--color-sunken)",
    title: (
      <>
        <b className="font-semibold">Павел</b>: «Делаете All-on-4?»
      </>
    ),
    meta: (
      <>
        <Headset className="size-3.5 shrink-0 text-warn" />
        Передано администратору
      </>
    ),
    more: "в документах этого нет",
  },
  {
    id: "sergey",
    avatar: letter("С"),
    color: "#c2410c",
    title: (
      <>
        <b className="font-semibold">Сергей</b>: «А кофе после отбеливания можно?»
      </>
    ),
    meta: (
      <>
        <Check className="size-3.5 shrink-0 text-accent" />
        Бот понял уточнение
      </>
    ),
    more: "Источник: Частые вопросы",
  },
  {
    id: "igor",
    avatar: letter("И"),
    color: "#a16207",
    title: (
      <>
        <b className="font-semibold">Администратор</b> ответил Игорю
      </>
    ),
    meta: (
      <>
        <Headset className="size-3.5 shrink-0 text-accent" />
        Из админки
      </>
    ),
    more: "бот в этом чате молчит",
  },
];

const VISIBLE = 3;
const STEP_MS = 4200;

// Место в стопке: сдвиг вниз (в долях шага), уменьшение и прозрачность. Четвёртое место — уходящая карточка
const PLACE = [
  { y: 0, scale: 1, opacity: 1 },
  { y: 1, scale: 0.95, opacity: 0.9 },
  { y: 2, scale: 0.9, opacity: 0.7 },
  { y: 2.6, scale: 0.85, opacity: 0 },
];

export function HeroFeed() {
  const [start, setStart] = useState(0);

  useEffect(() => {
    // Крутится и при «Уменьшить движение»: смена карточек мягкая, без резких сдвигов
    const timer = setInterval(() => setStart((s) => (s + EVENTS.length - 1) % EVENTS.length), STEP_MS);
    return () => clearInterval(timer);
  }, []);

  // Карточки стоят на месте в DOM (ключ — событие) и только переезжают: меняются сдвиг и масштаб,
  // ширина постоянная — поэтому ничего не растягивается. Новая проявляется сверху
  const shown = PLACE.map((_, i) => EVENTS[(start + i) % EVENTS.length]);

  return (
    <div
      className="relative isolate mx-auto mt-12 h-[calc(var(--step)*2+var(--card))] w-full max-w-md [--card:76px] [--step:60px] sm:[--card:64px] sm:[--step:56px]"
      aria-label="События бота"
    >
      <div className="hero-glow pointer-events-none absolute -inset-x-24 -inset-y-16 -z-10" />
      {shown.map((e, i) => (
        <div
          key={e.id}
          className="feed-card absolute inset-x-0 top-0 flex h-(--card) origin-top items-center gap-3 rounded-2xl border border-line bg-surface px-3.5 text-left shadow-[0_18px_40px_-24px_rgba(17,23,22,.35)] sm:px-4"
          style={{
            translate: `0 calc(var(--step) * ${PLACE[i].y})`,
            scale: PLACE[i].scale,
            opacity: PLACE[i].opacity,
            zIndex: PLACE.length - i,
          }}
          aria-hidden={i >= VISIBLE}
        >
          <span className="grid size-9 shrink-0 place-items-center rounded-full" style={{ background: e.color }}>
            {e.avatar}
          </span>
          <span className="min-w-0 flex-1">
            <span className="line-clamp-2 text-[13px] leading-[18px] text-ink sm:line-clamp-1 sm:text-sm sm:leading-5">
              {e.title}
            </span>
            <span className="mt-0.5 flex items-center gap-1 text-xs whitespace-nowrap text-ink-3">
              {e.meta}
              <span className="truncate max-sm:hidden">· {e.more}</span>
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}
