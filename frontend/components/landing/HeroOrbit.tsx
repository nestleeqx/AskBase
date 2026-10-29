import { CalendarCheck, Database, Globe, Headset, Send, Sparkles, UserRound } from "lucide-react";
import type { ReactNode } from "react";
import { HeroFeed } from "./HeroFeed";

// Круги первого экрана: радиусы в px от центра заголовка
const RINGS = [190, 340, 490, 650];

type Planet = { ring: number; angle: number; label: string; icon: ReactNode };

// На узком экране дальние круги уходят за край — их иконки прячем
const HIDE = ["", "max-sm:hidden", "max-md:hidden", "max-lg:hidden"];

const fileBadge = (text: string, color: string) => (
  <span className="text-[11px] font-bold tracking-tight" style={{ color }}>
    {text}
  </span>
);

// Что на кругах — то, с чем AskBase действительно работает: каналы, форматы, нейросеть, база.
// Угол 0° — вправо, отрицательный — вверх
const PLANETS: Planet[] = [
  { ring: 1, angle: 186, label: "Telegram", icon: <Send className="size-5 text-[#229ED9]" /> },
  { ring: 1, angle: -6, label: "Нейросеть", icon: <Sparkles className="size-5 text-accent" /> },
  { ring: 2, angle: 150, label: "PDF", icon: fileBadge("PDF", "#d4482f") },
  { ring: 2, angle: -146, label: "pgvector", icon: <Database className="size-5 text-ink-2" /> },
  { ring: 2, angle: 30, label: "DOCX", icon: fileBadge("DOCX", "#2b6cd9") },
  { ring: 2, angle: -34, label: "Запись", icon: <CalendarCheck className="size-5 text-success" /> },
  { ring: 3, angle: 196, label: "TXT", icon: fileBadge("TXT", "#465755") },
  { ring: 3, angle: -16, label: "Сайт", icon: <Globe className="size-5 text-info" /> },
  { ring: 3, angle: 162, label: "Администратор", icon: <Headset className="size-5 text-warn" /> },
  { ring: 3, angle: 18, label: "Заявки", icon: <UserRound className="size-5 text-ink-2" /> },
];

function Orbit() {
  return (
    <div
      aria-hidden
      className="orbit-fade pointer-events-none absolute inset-x-0 top-0 -z-10 h-[820px] overflow-hidden"
    >
      <div className="absolute top-[300px] left-1/2">
        {RINGS.map((r, i) => (
          <span
            key={r}
            className="absolute rounded-full border border-line"
            style={{ width: r * 2, height: r * 2, left: -r, top: -r }}
          >
            {/* Бирюзовый «сигнал» обходит круг: хвост-дуга и светящаяся точка впереди */}
            <span
              className="orbit-spin absolute -inset-px rounded-full"
              style={{ animationDuration: `${30 + i * 10}s`, animationDirection: i % 2 ? "reverse" : "normal" }}
            >
              <span className="orbit-arc absolute inset-0 rounded-full" />
              <span className="orbit-dot absolute top-0 left-1/2" />
            </span>
          </span>
        ))}
        {/* Волна раз в 7 секунд расходится от центра по кругам */}
        {[0, 1].map((n) => (
          <span key={n} className="orbit-ripple" style={{ animationDelay: `${-n * 7}s` }} />
        ))}
        {/* Светлая подложка под заголовком и текстом: круги и сигналы за ними едва видны и не мешают читать.
            Иконки идут после неё и остаются чёткими */}
        <span className="absolute top-[-40px] left-0 h-[460px] w-[880px] -translate-x-1/2 -translate-y-1/2 bg-[radial-gradient(closest-side,#fff_45%,rgba(255,255,255,.7)_75%,transparent)]" />
        {PLANETS.map((p, i) => {
          const r = RINGS[p.ring];
          const a = (p.angle * Math.PI) / 180;
          // Снаружи — позиция на круге, внутри — парение: иначе анимация сбивала бы центрирование
          return (
            <span
              key={p.label}
              title={p.label}
              className={`absolute -translate-x-1/2 -translate-y-1/2 ${HIDE[p.ring]}`}
              style={{ left: Math.round(r * Math.cos(a)), top: Math.round(r * Math.sin(a)) }}
            >
              <span
                className="float-slow grid size-14 place-items-center rounded-full border border-line bg-surface shadow-[0_10px_30px_-12px_rgba(17,23,22,.25)]"
                style={{ animationDelay: `${-i * 0.9}s` }}
              >
                {p.icon}
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

export function HeroOrbit({ children }: { children: ReactNode }) {
  return (
    <section className="relative isolate overflow-x-clip">
      <Orbit />
      <div className="mx-auto flex max-w-3xl flex-col items-center px-4 pt-14 pb-20 text-center sm:px-6 md:pt-20">
        {children}
        <HeroFeed />
      </div>
    </section>
  );
}
