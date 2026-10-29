export function plural(n: number, forms: [string, string, string]) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return forms[1];
  return forms[2];
}

const number = new Intl.NumberFormat("ru-RU");

/** «3 501» с неразрывным пробелом между разрядами. */
export function formatNumber(n: number) {
  return number.format(n);
}

/** Время в секундах: «0,8 с», «12 с». Неразрывный пробел перед «с». Меньше 0,1 с — «0,1 с», а не «0,0 с». */
export function formatSeconds(ms: number) {
  const s = Math.max(ms, 100) / 1000;
  const text =
    s < 10 ? s.toLocaleString("ru-RU", { maximumFractionDigits: 1, minimumFractionDigits: 1 }) : Math.round(s);
  return `${text} с`;
}

export function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`;
  return `${(bytes / 1024 / 1024).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} МБ`;
}

export const KIND_LABELS = { pdf: "PDF", docx: "DOCX", txt: "TXT", url: "Страница сайта" } as const;

const timeFmt = new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" });
const dayFmt = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" });

function dayDiff(date: Date, now = new Date()) {
  const start = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  return Math.round((start(now) - start(date)) / 86_400_000);
}

/** «14:05», «вчера, 14:05», «12 окт., 14:05» — время сообщения. */
export function formatTime(iso: string) {
  const date = new Date(iso);
  const days = dayDiff(date);
  const time = timeFmt.format(date);
  if (days === 0) return time;
  if (days === 1) return `вчера, ${time}`;
  return `${dayFmt.format(date)}, ${time}`;
}

/** Коротко для списка: «сейчас», «5 мин», «14:05», «вчера», «12 окт.». */
export function formatShortTime(iso: string) {
  const date = new Date(iso);
  const minutes = Math.floor((Date.now() - date.getTime()) / 60_000);
  if (minutes < 1) return "сейчас";
  if (minutes < 60) return `${minutes} мин`;
  const days = dayDiff(date);
  if (days === 0) return timeFmt.format(date);
  if (days === 1) return "вчера";
  return dayFmt.format(date);
}

/** Маска российского номера: «+7 (495) 200-18-18». prev — значение до правки: если стёрли
 *  скобку или дефис, убираем и цифру перед ним — иначе маска вернула бы символ на место. */
export function maskPhone(value: string, prev = "") {
  let digits = value.replace(/\D/g, "");
  if (value.length < prev.length && digits === prev.replace(/\D/g, "")) digits = digits.slice(0, -1);
  if (digits[0] === "8" || digits[0] === "7") digits = digits.slice(1);
  digits = digits.slice(0, 10);
  if (!digits) return "";
  const [a, b, c, d] = [digits.slice(0, 3), digits.slice(3, 6), digits.slice(6, 8), digits.slice(8, 10)];
  let out = `+7 (${a}`;
  if (b) out += `) ${b}`;
  if (c) out += `-${c}`;
  if (d) out += `-${d}`;
  return out;
}
