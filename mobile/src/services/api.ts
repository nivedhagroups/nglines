import Constants from "expo-constants";
import {
  clearSession,
  getAccessToken,
  getRefreshToken,
  storeSession,
} from "./session";
import type { ApiErrorShape, SessionPayload } from "../types/api";

export const API_BASE =
  process.env.EXPO_PUBLIC_API_URL ??
  (Constants.expoConfig?.extra?.apiBaseUrl as string | undefined) ??
  "http://localhost:8000/api/v1";

let activeBusinessId: string | null = null;
let refreshInFlight: Promise<string | null> | null = null;

export function setActiveBusinessHeader(id: string | null): void {
  activeBusinessId = id;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly fields: { field: string; message: string }[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    const refreshToken = await getRefreshToken();
    if (!refreshToken) return null;
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) {
      await clearSession();
      return null;
    }
    const payload = (await response.json()) as { data: SessionPayload };
    await storeSession(payload.data);
    return payload.data.access_token;
  })();
  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

async function decodeError(response: Response): Promise<ApiError> {
  let payload: ApiErrorShape | undefined;
  try {
    payload = (await response.json()) as ApiErrorShape;
  } catch {
    payload = undefined;
  }
  return new ApiError(
    payload?.error?.message ?? "Unable to complete the request.",
    response.status,
    payload?.error?.code ?? "request_error",
    payload?.error?.fields ?? [],
  );
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  retryAuth = true,
): Promise<T> {
  const headers = new Headers(options.headers);
  const isForm = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (!isForm && options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (activeBusinessId) headers.set("X-Business-ID", activeBusinessId);
  const accessToken = await getAccessToken();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch {
    throw new ApiError("You appear to be offline. Check your connection and retry.", 0, "network_error");
  }
  const authEndpointsWithoutRefresh = ["/auth/otp/request", "/auth/otp/verify", "/auth/refresh", "/auth/logout"];
  if (response.status === 401 && retryAuth && !authEndpointsWithoutRefresh.includes(path)) {
    const renewed = await refreshAccessToken();
    if (renewed) return apiRequest<T>(path, options, false);
  }
  if (!response.ok) throw await decodeError(response);
  if (response.status === 204) return undefined as T;
  const result = (await response.json()) as { data: T } | T;
  if (typeof result === "object" && result !== null && "data" in result) {
    if ("page" in result) return result as T;
    return result.data as T;
  }
  return result as T;
}

export const authApi = {
  requestOtp: (identifier: string) =>
    apiRequest<{ challenge_id: string; expires_in_seconds: number }>(
      "/auth/otp/request",
      { method: "POST", body: JSON.stringify({ identifier }) },
      false,
    ),
  verifyOtp: (challengeId: string, code: string) =>
    apiRequest<SessionPayload>(
      "/auth/otp/verify",
      { method: "POST", body: JSON.stringify({ challenge_id: challengeId, code }) },
      false,
    ),
  logout: (refreshToken: string) =>
    apiRequest<void>("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) }),
  me: () => apiRequest<SessionPayload["user"] & { businesses: SessionPayload["businesses"] }>("/auth/me"),
};