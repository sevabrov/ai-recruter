/**
 * Thin fetch wrapper for the FastAPI backend (Phase 2+).
 *
 * Only public config lives here. Provider keys — Brave, ScrapeGraphAI, OpenAI —
 * are never referenced from front-end code; the browser talks to our backend
 * and nothing else.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | string[] | undefined>;
  signal?: AbortSignal;
};

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, signal } = options;
  const url = new URL(`${API_BASE_URL}${path}`);

  for (const [key, value] of Object.entries(query ?? {})) {
    if (value == null) continue;
    if (Array.isArray(value)) value.forEach((item) => url.searchParams.append(key, item));
    else url.searchParams.set(key, String(value));
  }

  const response = await fetch(url, {
    method,
    signal,
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    let detail: unknown;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text().catch(() => undefined);
    }
    throw new ApiError(`${method} ${path} failed with ${response.status}`, response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
