import * as SecureStore from "expo-secure-store";
import type { SessionPayload } from "../types/api";

const ACCESS_KEY = "ng.access-token";
const REFRESH_KEY = "ng.refresh-token";
const BUSINESS_KEY = "ng.active-business";

export async function storeSession(session: SessionPayload): Promise<void> {
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_KEY, session.access_token),
    SecureStore.setItemAsync(REFRESH_KEY, session.refresh_token),
  ]);
}

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_KEY);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_KEY);
}

export async function clearSession(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_KEY),
    SecureStore.deleteItemAsync(REFRESH_KEY),
    SecureStore.deleteItemAsync(BUSINESS_KEY),
  ]);
}

export async function storeActiveBusiness(id: string): Promise<void> {
  await SecureStore.setItemAsync(BUSINESS_KEY, id);
}

export async function getActiveBusiness(): Promise<string | null> {
  return SecureStore.getItemAsync(BUSINESS_KEY);
}