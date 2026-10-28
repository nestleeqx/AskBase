import type { ChatReply, Conversation, Doc, DocumentChunks, DocumentList, SearchResult } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

const VISITOR_KEY = "askbase:visitor";

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
};
