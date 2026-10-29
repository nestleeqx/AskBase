import type {
  Analytics,
  AuthStatus,
  Booking,
  BotSettings,
  BotSettingsValues,
  BookingList,
  BookingStatus,
  ChatReply,
  Conversation,
  DialogDetail,
  DialogList,
  Doc,
  DocumentChunks,
  DocumentList,
  SearchResult,
  TelegramStatus,
  UnansweredItem,
  UnansweredList,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

const VISITOR_KEY = "askbase:visitor";
const OWNER_KEY = "askbase:owner";

/** Токен владельца клиники после входа по паролю. Нет токена — гостевой режим. */
export function ownerToken(): string | null {
  try {
    return localStorage.getItem(OWNER_KEY);
  } catch {
    return null;
  }
}

export function setOwnerToken(token: string | null) {
  try {
    if (token) localStorage.setItem(OWNER_KEY, token);
    else localStorage.removeItem(OWNER_KEY);
  } catch {}
}

/** Анонимный id посетителя: свои загруженные документы видит только он. */
export function visitorId(): string {
  let id: string | null = null;
  try {
    id = localStorage.getItem(VISITOR_KEY);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(VISITOR_KEY, id);
    }
  } catch {
    // Приватный режим без localStorage — id живёт до перезагрузки
    id ??= (globalThis as { __visitor?: string }).__visitor ??= crypto.randomUUID();
  }
  return id;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

const NETWORK_ERROR = "Не удалось связаться с сервером. Проверьте подключение к интернету и попробуйте ещё раз.";
const SERVER_ERROR = "Что-то пошло не так. Попробуйте ещё раз через минуту.";

/** Текст ошибки для пользователя: понятные сообщения API показываем как есть,
 *  технические (коды 5xx, ответы валидации FastAPI) заменяем общими формулировками. */
async function errorMessage(resp: Response): Promise<string> {
  let detail: unknown;
  try {
    detail = (await resp.json()).detail;
  } catch {}
  if (typeof detail === "string" && resp.status < 500) return detail;
  if (resp.status === 422) return "Проверьте введённые данные и попробуйте ещё раз.";
  return SERVER_ERROR;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Visitor-Id", visitorId());
  const owner = ownerToken();
  if (owner) headers.set("X-Owner-Token", owner);
  // FormData сам выставит multipart с границей — тип задаём только для JSON
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  let resp: Response;
  try {
    resp = await fetch(API_URL + path, { ...init, headers });
  } catch {
    throw new ApiError(NETWORK_ERROR, 0);
  }
  if (!resp.ok) throw new ApiError(await errorMessage(resp), resp.status);
  return resp.status === 204 ? (undefined as T) : resp.json();
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  auth: () => request<AuthStatus>("/api/auth"),
  login: (password: string) => request<{ token: string }>("/api/auth/login", json("POST", { password })),

  documents: () => request<DocumentList>("/api/documents"),
  uploadFile: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Doc>("/api/documents", { method: "POST", body: form });
  },
  uploadUrl: (url: string) => request<Doc>("/api/documents/url", json("POST", { url })),
  chunks: (id: string) => request<DocumentChunks>(`/api/documents/${id}/chunks`),
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, json("DELETE")),
  /** Оригинал документа демо-базы — открывается прямо в браузере. */
  fileUrl: (id: string) => `${API_URL}/api/documents/${id}/file`,

  search: (question: string) => request<SearchResult>("/api/search", json("POST", { question })),

  /** Без conversationId начинается новый диалог. */
  ask: (question: string, conversationId?: string | null) =>
    request<ChatReply>("/api/chat", json("POST", { question, conversation_id: conversationId ?? undefined })),
  conversation: (id: string) => request<Conversation>(`/api/chat/${id}`),

  dialogs: (q = "", waiting = false) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (waiting) params.set("waiting", "true");
    const query = params.toString();
    return request<DialogList>(`/api/dialogs${query ? `?${query}` : ""}`);
  },
  /** Последние limit сообщений переписки: при прокрутке вверх админка просит больше */
  dialog: (id: string, limit = 50) => request<DialogDetail>(`/api/dialogs/${id}?limit=${limit}`),
  reply: (id: string, text: string) => request<DialogDetail>(`/api/dialogs/${id}/reply`, json("POST", { text })),
  release: (id: string) => request<DialogDetail>(`/api/dialogs/${id}/release`, json("POST")),

  bookings: () => request<BookingList>("/api/bookings"),
  setBooking: (id: string, status: BookingStatus) => request<Booking>(`/api/bookings/${id}`, json("PATCH", { status })),

  telegram: () => request<TelegramStatus>("/api/telegram"),
  telegramLink: () => request<{ url: string }>("/api/telegram/link", json("POST")),

  unanswered: (status: "open" | "resolved") => request<UnansweredList>(`/api/unanswered?status=${status}`),
  resolve: (id: number, resolved: boolean) =>
    request<UnansweredItem>(`/api/unanswered/${id}/resolve`, json("POST", { resolved })),
  answerToBase: (id: number, question: string, answer: string) =>
    request<UnansweredItem>(`/api/unanswered/${id}/answer`, json("POST", { question, answer })),

  analytics: () => request<Analytics>("/api/analytics"),

  settings: () => request<BotSettings>("/api/settings"),
  saveSettings: (values: BotSettingsValues) => request<BotSettings>("/api/settings", json("PUT", values)),
  resetSettings: () => request<BotSettings>("/api/settings", json("DELETE")),
};
