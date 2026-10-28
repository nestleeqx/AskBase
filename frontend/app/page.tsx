import {
  ArrowRight,
  BarChart3,
  BookOpenCheck,
  CalendarCheck,
  CircleHelp,
  Clock,
  FileText,
  Headset,
  Layers,
  MessageCircleQuestion,
  MessagesSquare,
  Moon,
  Repeat,
  SearchCheck,
  ShieldCheck,
  Upload,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { CountUp } from "@/components/landing/CountUp";
import { HeroChat } from "@/components/landing/HeroChat";
import { Reveal } from "@/components/landing/Reveal";
import { TelegramCta } from "@/components/landing/TelegramCta";
import { Logo } from "@/components/Logo";

export const metadata: Metadata = {
  title: "AskBase — бот, который отвечает клиентам по вашим документам",
  description:
    "Telegram-бот для сервисного бизнеса: отвечает на вопросы клиентов строго по документам компании, записывает на приём и передаёт вопрос администратору, если ответа нет.",
};

const PRIMARY =
  "inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-accent px-6 font-medium whitespace-nowrap text-white shadow-[0_10px_30px_-10px_rgba(13,148,136,.8)] transition-colors hover:bg-accent-hover";
const SECONDARY =
  "inline-flex h-12 items-center justify-center gap-2 rounded-xl border border-line bg-surface px-6 font-medium whitespace-nowrap text-ink transition-colors hover:bg-sunken";

const PROBLEMS: { icon: ReactNode; title: string; text: string }[] = [
  {
    icon: <Repeat className="size-5" />,
    title: "Одни и те же вопросы",
    text: "«Сколько стоит?», «Работаете в субботу?», «Что взять с собой?» — администратор весь день отвечает на то, что давно написано в прайсе и правилах.",
  },
  {
    icon: <Moon className="size-5" />,
    title: "Ночью ответить некому",
    text: "Клиент пишет вечером или в выходной, не получает ответа и уходит туда, где ответили быстрее.",
  },
  {
    icon: <MessageCircleQuestion className="size-5" />,
    title: "Обычный чат-бот выдумывает",
    text: "Нейросеть без опоры на документы уверенно называет несуществующие цены и услуги. Клиент верит — а потом приходит спорить.",
  },
];

const STEPS: { icon: ReactNode; title: string; text: string }[] = [
  {
    icon: <Upload className="size-5" />,
    title: "Загрузите документы",
    text: "Прайс в PDF, список врачей в DOCX, FAQ в TXT или страницу сайта. Через несколько секунд бот уже отвечает по ним.",
  },
  {
    icon: <SearchCheck className="size-5" />,
    title: "Бот ищет ответ",
    text: "По смыслу и по словам сразу: находит «профгигиену», даже если спросили про «чистку», и фамилию врача с опечаткой.",
  },
  {
    icon: <FileText className="size-5" />,
    title: "Отвечает со ссылкой",
    text: "Только по найденным фрагментам — и называет документ-источник. Ответ, который нечем подтвердить, бот не отправит.",
  },
  {
    icon: <Headset className="size-5" />,
    title: "Не знает — зовёт человека",
    text: "«Уточню у администратора и вернусь». Вопрос попадает в админку, менеджер получает уведомление в Telegram.",
  },
];

const FEATURES: { icon: ReactNode; title: string; text: string; tone: string }[] = [
  {
    icon: <BookOpenCheck className="size-5" />,
    title: "Ответы с источником",
    text: "Каждый ответ — из документов клиники, под ним «Источник: Прайс-лист». В админке видно, какие фрагменты нашлись.",
    tone: "bg-accent-soft text-accent",
  },
  {
    icon: <MessagesSquare className="size-5" />,
    title: "Понимает уточнения",
    text: "«А гарантия на неё какая?» после вопроса о коронке — бот помнит диалог и отвечает про коронку.",
    tone: "bg-info-soft text-info",
  },
  {
    icon: <CalendarCheck className="size-5" />,
    title: "Запись на приём",
    text: "Имя, телефон кнопкой «Поделиться номером», повод и удобное время. Заявка — в админку и менеджеру в Telegram.",
    tone: "bg-success-soft text-success",
  },
  {
    icon: <Headset className="size-5" />,
    title: "Передача человеку",
    text: "Администратор отвечает клиенту прямо из админки, бот в это время молчит. «Вернуть боту» — одной кнопкой.",
    tone: "bg-warn-soft text-warn",
  },
  {
    icon: <CircleHelp className="size-5" />,
    title: "«Бот не смог ответить»",
    text: "Вопросы, которых нет в базе, собираются в отдельный раздел. Ответ, написанный там, бот сразу берёт в работу.",
    tone: "bg-danger-soft text-danger",
  },
  {
    icon: <BarChart3 className="size-5" />,
    title: "Аналитика и настройки",
    text: "Диалоги за неделю, доля ответов, топ тем. Приветствие, тон ответов и контакты меняются без программиста.",
    tone: "bg-sunken text-ink-2",
  },
];

export default function Home() {
  return (
    <div className="min-h-full overflow-x-clip">
      <header className="sticky top-0 z-30 border-b border-line/70 bg-canvas/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-6">
          <Link href="/" aria-label="AskBase — на главную">
            <Logo />
          </Link>
          <nav className="ml-auto hidden items-center gap-6 text-sm text-ink-2 md:flex">
            <a href="#how" className="hover:text-ink">
              Как работает
            </a>
            <a href="#features" className="hover:text-ink">
              Возможности
            </a>
            <a href="#accuracy" className="hover:text-ink">
              Точность
            </a>
          </nav>
          <Link
            href="/login"
            className="ml-auto inline-flex h-10 items-center gap-1.5 rounded-xl bg-accent px-4 text-sm font-medium text-white transition-colors hover:bg-accent-hover md:ml-0"
          >
            Открыть демо
          </Link>
        </div>
      </header>

      <section className="relative">
        <div className="dot-grid pointer-events-none absolute inset-0 -z-10" />
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 pt-12 pb-16 sm:px-6 md:pt-20 lg:grid-cols-[1.05fr_1fr]">
          <div>
            <p className="rise inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-ink-2 shadow-[0_1px_2px_rgba(16,32,31,.05)]">
              <span className="size-1.5 rounded-full bg-accent" />
              Telegram-бот на базе знаний компании
            </p>
            <h1
              className="rise mt-5 text-4xl leading-[1.05] font-semibold tracking-tight text-balance text-ink sm:text-5xl"
              style={{ animationDelay: "80ms" }}
            >
              Бот отвечает клиентам по вашим документам{" "}
              <span className="bg-gradient-to-r from-accent to-[#4fd1bd] bg-clip-text text-transparent">
                и не выдумывает
              </span>
            </h1>
            <p className="rise mt-5 max-w-xl text-lg leading-relaxed text-ink-2" style={{ animationDelay: "160ms" }}>
              AskBase знает ваш прайс, врачей и правила. Отвечает на вопросы в Telegram круглосуточно, записывает на
              приём, а если ответа в документах нет — честно передаёт вопрос администратору.
            </p>
            <div className="rise mt-8 flex flex-col gap-3 sm:flex-row" style={{ animationDelay: "240ms" }}>
              <Link href="/login" className={PRIMARY}>
                Открыть демо-админку
                <ArrowRight className="size-4" />
              </Link>
              <TelegramCta className={SECONDARY} />
            </div>
            <p className="rise mt-4 text-sm text-ink-3" style={{ animationDelay: "320ms" }}>
              Без регистрации · демо-клиника «Белая линия» с прайсом, врачами и правилами записи
            </p>
          </div>
          <HeroChat />
        </div>
      </section>

      <section id="accuracy" className="mx-auto grid max-w-6xl scroll-mt-16 gap-3 px-4 py-12 sm:grid-cols-3 sm:px-6">
        {[
          {
            value: <CountUp to={19} />,
            suffix: " из 20",
            text: "верных ответов на тестовом наборе вопросов по документам клиники",
          },
          {
            value: <CountUp to={5} />,
            suffix: " из 5",
            text: "вопросов вне базы («сколько стоит ремонт машины?») бот передал администратору",
          },
          { value: "≈2", suffix: " с", text: "медиана времени ответа — от вопроса до готового ответа с источником" },
        ].map((m, i) => (
          <Reveal key={m.text} delay={i * 100} className="rounded-2xl border border-line bg-surface p-6">
            <p className="text-4xl font-semibold tracking-tight text-ink">
              {m.value}
              <span className="text-ink-3">{m.suffix}</span>
            </p>
            <p className="mt-2 text-sm text-ink-2">{m.text}</p>
          </Reveal>
        ))}
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <Reveal>
          <h2 className="text-3xl font-semibold tracking-tight text-ink">Знакомо?</h2>
        </Reveal>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {PROBLEMS.map((p, i) => (
            <Reveal key={p.title} delay={i * 120} className="rounded-2xl border border-line bg-surface p-6">
              <span className="grid size-11 place-items-center rounded-xl bg-danger-soft text-danger">{p.icon}</span>
              <h3 className="mt-4 font-semibold text-ink">{p.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-2">{p.text}</p>
            </Reveal>
          ))}
        </div>
      </section>

      <section id="how" className="scroll-mt-16 bg-ink text-white">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <Reveal>
            <h2 className="text-3xl font-semibold tracking-tight">Как работает</h2>
            <p className="mt-2 max-w-xl text-white/60">
              От вопроса клиента до ответа со ссылкой на документ — 2–3 секунды.
            </p>
          </Reveal>
          <Reveal className="relative mt-10">
            {/* Линия между шагами прорисовывается слева направо; карточки непрозрачные — она видна только в промежутках */}
            <div className="absolute top-11 right-[12%] left-[12%] hidden h-px bg-white/10 lg:block">
              <div className="step-line h-full bg-gradient-to-r from-accent via-[#4fd1bd] to-glow" />
            </div>
            <ol className="relative grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {STEPS.map((s, i) => (
                <li
                  key={s.title}
                  className="rise relative rounded-2xl bg-[#1b2c2b] p-5"
                  style={{ animationDelay: `${i * 150}ms` }}
                >
                  <span className="flex items-center justify-between">
                    <span className="grid size-12 place-items-center rounded-2xl bg-accent text-white shadow-[0_8px_24px_-8px_rgba(13,148,136,.9)]">
                      {s.icon}
                    </span>
                    <span className="text-sm font-semibold text-white/40">0{i + 1}</span>
                  </span>
                  <h3 className="mt-4 font-semibold">{s.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-white/65">{s.text}</p>
                </li>
              ))}
            </ol>
          </Reveal>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-16 sm:px-6 lg:grid-cols-2">
        <Reveal>
          <p className="text-sm font-medium text-accent">Честность важнее ответа любой ценой</p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-balance text-ink">
            Нет в документах — нет ответа. Есть администратор
          </h2>
          <p className="mt-4 text-ink-2">
            Нейросеть отвечает только по найденным фрагментам и называет, на какие опиралась. Система проверяет это
            сама: ответ без подтверждённого источника клиент не увидит — вопрос уйдёт человеку.
          </p>
          <ul className="mt-6 space-y-2.5 text-sm text-ink-2">
            {[
              "Вопрос вне базы — «Уточню у администратора», а не догадка",
              "Ничего похожего в базе нет — нейросеть даже не вызывается, токены целы",
              "Администратор отвечает из админки — и тут же может добавить ответ в базу",
            ].map((t) => (
              <li key={t} className="flex gap-2.5">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-accent" />
                {t}
              </li>
            ))}
          </ul>
        </Reveal>
        <Reveal
          delay={150}
          className="rounded-3xl border border-line bg-surface p-5 shadow-[0_24px_50px_-32px_rgba(16,32,31,.4)]"
        >
          <p className="text-xs font-medium text-ink-3">Как бот искал ответ</p>
          <p className="mt-2 text-sm font-medium text-ink">«Сколько стоит ремонт машины?»</p>
          <ol className="mt-3 space-y-1.5 text-xs">
            {/* Настоящий разбор этого вопроса из тестового прогона (scripts/evaluate.py) */}
            {[
              ["Правила записи на приём · Острая боль", "0,17"],
              ["Прайс-лист · Профилактика и гигиена", "0,36"],
              ["Прайс-лист · Протезирование", "0,35"],
            ].map(([title, score], i) => (
              <li key={title} className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-2">
                <span className="w-3 text-ink-3 tabular-nums">{i + 1}</span>
                <span className="flex-1 truncate text-ink">{title}</span>
                <span className="text-ink-3 tabular-nums">{score}</span>
              </li>
            ))}
          </ol>
          <div className="mt-3 rounded-xl border border-warn/25 bg-warn-soft px-3.5 py-2.5 text-sm">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-warn">
              <Headset className="size-3.5" />
              Вопрос передан администратору
            </p>
            <p className="mt-0.5 text-ink">Уточню у администратора и вернусь с ответом.</p>
          </div>
          <p className="mt-3 flex items-center gap-1.5 text-xs text-ink-3">
            <Clock className="size-3.5" />
            Нейросеть не нашла ответа во фрагментах — 1,5 с
          </p>
        </Reveal>
      </section>

      <section id="features" className="mx-auto max-w-6xl scroll-mt-16 px-4 py-12 sm:px-6">
        <Reveal>
          <h2 className="text-3xl font-semibold tracking-tight text-ink">Возможности</h2>
        </Reveal>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <Reveal
              key={f.title}
              delay={(i % 3) * 100}
              className="group rounded-2xl border border-line bg-surface p-6 transition-[box-shadow,translate] duration-300 hover:-translate-y-1 hover:shadow-[0_20px_40px_-24px_rgba(16,32,31,.35)]"
            >
              <span
                className={`grid size-11 place-items-center rounded-xl transition-transform duration-300 group-hover:scale-110 ${f.tone}`}
              >
                {f.icon}
              </span>
              <h3 className="mt-4 font-semibold text-ink">{f.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{f.text}</p>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <Reveal className="relative overflow-hidden rounded-3xl bg-ink p-6 text-white sm:p-12">
          <div className="hero-glow pointer-events-none absolute -inset-20 opacity-80" />
          <div className="relative">
            <h2 className="max-w-2xl text-3xl font-semibold tracking-tight text-balance">
              Спросите бота клиники «Белая линия» о чём угодно
            </h2>
            <p className="mt-3 max-w-xl text-white/70">
              Цены, врачи, подготовка к процедурам, запись. Загрузите свой документ — и посмотрите, как бот начнёт
              отвечать по нему через несколько секунд.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link href="/login" className={PRIMARY}>
                Открыть демо-админку
                <ArrowRight className="size-4" />
              </Link>
              <TelegramCta className="inline-flex h-12 items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/5 px-6 font-medium whitespace-nowrap text-white transition-colors hover:bg-white/10" />
            </div>
          </div>
        </Reveal>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-6 text-sm text-ink-3 sm:px-6">
          <span className="inline-flex items-center gap-1.5">
            <Layers className="size-4" />
            AskBase — демо-проект. Клиника «Белая линия», врачи и цены вымышлены.
          </span>
          <a
            href="https://github.com/nestleeqx/AskBase"
            target="_blank"
            rel="noreferrer"
            className="ml-auto hover:text-ink"
          >
            Код на GitHub
          </a>
        </div>
      </footer>
    </div>
  );
}
