const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ADMIN_API_KEY = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? "dev-admin-key";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type RequestOptions = RequestInit & {
  retries?: number;
  backoffMs?: number;
  timeoutMs?: number;
  admin?: boolean;
};

function isLoopbackHost(hostname: string): boolean {
  const host = hostname.trim().toLowerCase();
  return host === "localhost" || host === "127.0.0.1" || host === "::1" || host === "0.0.0.0";
}

function resolveApiBaseUrl(): string {
  const fallback = API_URL.replace(/\/+$/, "");

  try {
    const parsed = new URL(fallback);
    if (typeof window !== "undefined") {
      const currentHost = window.location.hostname;
      if (isLoopbackHost(parsed.hostname) && !isLoopbackHost(currentHost)) {
        parsed.hostname = currentHost;
      }
    }
    return parsed.toString().replace(/\/+$/, "");
  } catch {
    return fallback;
  }
}

function resolveWsBaseUrl(): string {
  const resolvedApiBase = resolveApiBaseUrl();

  try {
    const parsed = new URL(resolvedApiBase);
    const pathname = parsed.pathname.replace(/\/+$/, "");
    if (pathname.endsWith("/api/v1")) {
      parsed.pathname = pathname.slice(0, -"/api/v1".length) || "/";
    }
    return parsed.toString().replace(/\/+$/, "");
  } catch {
    return resolvedApiBase.replace(/\/api\/v1\/?$/, "");
  }
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

export async function fetchJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const retries = options.retries ?? 1;
  const backoffMs = options.backoffMs ?? 400;
  const timeoutMs = options.timeoutMs ?? 7000;
  const url = `${resolveApiBaseUrl()}${path}`;

  const headers = new Headers(options.headers ?? {});
  headers.set("Content-Type", "application/json");
  if (options.admin) {
    headers.set("X-API-Key", ADMIN_API_KEY);
  }

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort("request_timeout"), timeoutMs);

    const externalSignal = options.signal;
    const abortFromExternalSignal = () => controller.abort("request_aborted");
    if (externalSignal) {
      if (externalSignal.aborted) {
        controller.abort("request_aborted");
      } else {
        externalSignal.addEventListener("abort", abortFromExternalSignal, { once: true });
      }
    }

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers,
        cache: "no-store",
      });

      if (!response.ok) {
        let detail = response.statusText;
        try {
          const body = (await response.json()) as { detail?: string };
          detail = body.detail ?? detail;
        } catch {
          // no-op
        }
        throw new ApiError(detail, response.status);
      }

      return (await response.json()) as T;
    } catch (error) {
      const isLastAttempt = attempt === retries;
      if (isLastAttempt) {
        throw error;
      }
      await sleep(backoffMs * (attempt + 1));
    } finally {
      clearTimeout(timeout);
      if (externalSignal) {
        externalSignal.removeEventListener("abort", abortFromExternalSignal);
      }
    }
  }

  throw new ApiError("Request failed", 500);
}

export function wsUrl(path: string): string {
  const normalized = resolveWsBaseUrl().replace(/^http/, "ws");
  return `${normalized}${path}`;
}
