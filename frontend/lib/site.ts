// Адрес сайта для canonical и Open Graph. Если NEXT_PUBLIC_SITE_URL не задан,
// на Vercel берём адрес продакшена, который платформа сама передаёт в сборку Next.js.
const vercelUrl = process.env.NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL;

export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL || (vercelUrl ? `https://${vercelUrl}` : "http://localhost:3000")
).replace(/\/$/, "");

export const SITE = {
  name: "AskBase",
  title: "AskBase — Telegram-бот, который отвечает по базе знаний",
  description:
    "Бот отвечает клиентам строго по документам компании: прайсу, FAQ, правилам. Если ответа нет — честно передаёт вопрос менеджеру. Документы и диалоги — в веб-админке.",
};

/** Страница «Правила записи» на демо-сайте клиники. */
export const CLINIC_RULES_PATH = "/clinic/pravila-zapisi.html";
