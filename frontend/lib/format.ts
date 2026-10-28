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
