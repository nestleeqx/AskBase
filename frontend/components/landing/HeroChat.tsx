"use client";

import { FileText, Headset, Send } from "lucide-react";
import { useEffect, useState } from "react";

// Сцена первого экрана — ответы настоящего бота демо-клиники: вопрос по прайсу, уточнение
// и вопрос, которого нет в документах. Идёт по кругу
type Line =
  { who: "client"; text: string } | { who: "bot"; text: string; source?: string } | { who: "handoff"; text: string };

const SCRIPT: Line[] = [
  { who: "client", text: "Сколько стоит удалить зуб мудрости?" },
  {
    who: "bot",
    text: "Удаление зуба мудрости — 6 500 ₽, ретинированного или дистопированного — 11 500 ₽.",
    source: "Прайс-лист",
  },
  { who: "client", text: "А гарантия на коронку из циркония?" },
  { who: "bot", text: "Гарантия на коронку из диоксида циркония — 3 года.", source: "Частые вопросы пациентов" },
  { who: "client", text: "Делаете протезирование All-on-4?" },
  { who: "bot", text: "Уточню у администратора и вернусь с ответом." },
  { who: "handoff", text: "Вопрос передан администратору — он ответит в этом чате" },
];

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function HeroChat() {
  const [shown, setShown] = useState(0);
  const [typing, setTyping] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      while (alive) {
        setShown(0);
        await sleep(600);
        for (let i = 0; i < SCRIPT.length && alive; i++) {
          if (SCRIPT[i].who === "bot") {
            setTyping(true);
            await sleep(1100);
            setTyping(false);
          }
          if (!alive) return;
          setShown(i + 1);
          await sleep(SCRIPT[i].who === "client" ? 700 : 1400);
        }
        await sleep(3200);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="relative">
      <div className="hero-glow pointer-events-none absolute -inset-16 -z-10" />
      <div className="float-slow overflow-hidden rounded-3xl border border-line bg-surface shadow-[0_30px_70px_-35px_rgba(16,32,31,.45)]">
        <div className="flex items-center gap-3 border-b border-line px-4 py-3">
          <span className="grid size-9 place-items-center rounded-full bg-gradient-to-br from-[#5eead4] to-[#0d9488] text-sm font-semibold text-white">
            Б
          </span>
          <div className="leading-tight">
            <p className="text-sm font-semibold text-ink">Белая линия — бот клиники</p>
            <p className="text-xs text-ink-3">{typing ? "печатает…" : "бот · отвечает по документам"}</p>
          </div>
          <Send className="ml-auto size-4 text-[#229ED9]" />
        </div>
        <div className="flex h-[360px] flex-col justify-end gap-2.5 bg-[#e3eeec] px-3.5 py-4 sm:h-[380px]">
          {SCRIPT.slice(0, shown).map((line, i) =>
            line.who === "client" ? (
              <p
                key={i}
                className="rise ml-auto max-w-[80%] rounded-2xl rounded-br-md bg-[#d7f5c6] px-3.5 py-2 text-[13px] text-ink"
              >
                {line.text}
              </p>
            ) : line.who === "bot" ? (
              <div key={i} className="rise max-w-[85%] rounded-2xl rounded-bl-md bg-surface px-3.5 py-2 text-[13px]">
                <p className="leading-relaxed text-ink">{line.text}</p>
                {line.source && (
                  <p className="mt-1 flex items-center gap-1 text-[11px] text-ink-3 italic">
                    <FileText className="size-3" />
                    Источник: {line.source}
                  </p>
                )}
              </div>
            ) : (
              <p
                key={i}
                className="rise mx-auto flex items-center gap-1.5 rounded-full bg-warn-soft px-3 py-1 text-[11px] font-medium text-warn"
              >
                <Headset className="size-3.5" />
                {line.text}
              </p>
            ),
          )}
          {typing && (
            <span className="fade-in flex w-fit items-center gap-1 rounded-2xl rounded-bl-md bg-surface px-3.5 py-3">
              {[0, 1, 2].map((d) => (
                <span
                  key={d}
                  className="size-1.5 animate-bounce rounded-full bg-ink-3"
                  style={{ animationDelay: `${d * 140}ms` }}
                />
              ))}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
