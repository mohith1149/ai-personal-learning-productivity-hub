/** Thin fetch wrapper. The session lives in an HttpOnly cookie, so no token is ever handled in JS. */

export class ApiError extends Error {
  status: number;
  retryAfter?: number;
  constructor(status: number, message: string, retryAfter?: number) {
    super(message);
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

type FastApiDetail = string | { loc?: (string | number)[]; msg: string }[] | undefined;

function messageFromDetail(detail: FastApiDetail, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    // 422 validation errors: "field: message"
    return detail
      .map((d) => {
        const field = d.loc?.filter((p) => p !== "body").join(".");
        return field ? `${field}: ${d.msg.replace(/^Value error, /, "")}` : d.msg;
      })
      .join("; ");
  }
  return fallback;
}

/** Build "?a=1&b=2", skipping empty values. */
export function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export async function api<T = unknown>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method: options.method ?? "GET",
      credentials: "same-origin",
      headers: options.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the backend running?");
  }

  if (res.status === 204) return undefined as T;

  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const detail = (data as { detail?: FastApiDetail } | null)?.detail;
    const retry = res.headers.get("Retry-After");
    throw new ApiError(
      res.status,
      messageFromDetail(detail, `Request failed (HTTP ${res.status})`),
      retry ? Number(retry) : undefined,
    );
  }
  return data as T;
}
