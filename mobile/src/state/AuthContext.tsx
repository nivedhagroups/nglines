import React, { createContext, useContext, useEffect, useState } from "react";
import { authApi } from "../services/api";
import {
  clearSession,
  getAccessToken,
  getActiveBusiness,
  getRefreshToken,
  storeActiveBusiness,
  storeSession,
} from "../services/session";
import { setActiveBusinessHeader } from "../services/api";
import type { BusinessAccess, SessionPayload, SessionUser } from "../types/api";
import { queryClient } from "./queryClient";
import { registerForPushNotifications, unregisterPushNotifications } from "../services/push";

type AuthState = {
  ready: boolean;
  user: SessionUser | null;
  businesses: BusinessAccess[];
  activeBusiness: BusinessAccess | null;
  login(identifier: string, password: string): Promise<void>;
  changePassword(currentPassword: string, newPassword: string): Promise<void>;
  selectBusiness(id: string): Promise<void>;
  logout(): Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: React.PropsWithChildren) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<SessionUser | null>(null);
  const [businesses, setBusinesses] = useState<BusinessAccess[]>([]);
  const [activeBusiness, setActiveBusinessState] = useState<BusinessAccess | null>(null);

  const activate = async (session: SessionPayload) => {
    setUser(session.user);
    setBusinesses(session.businesses);
    const savedId = await getActiveBusiness();
    const selected = session.businesses.find((business) => business.id === savedId) ?? session.businesses[0] ?? null;
    setActiveBusinessState(selected);
    setActiveBusinessHeader(selected?.id ?? null);
    if (selected) await storeActiveBusiness(selected.id);
  };

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const access = await getAccessToken();
        if (!access) return;
        const profile = await authApi.me();
        if (!mounted) return;
        const session: SessionPayload = {
          access_token: access,
          refresh_token: (await getRefreshToken()) ?? "",
          expires_in: 0,
          token_type: "Bearer",
          user: profile,
          businesses: profile.businesses,
        };
        await activate(session);
      } catch {
        if (mounted) {
          await clearSession();
          setUser(null);
          setBusinesses([]);
        }
      } finally {
        if (mounted) setReady(true);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!user) return;
    void registerForPushNotifications().catch(() => undefined);
  }, [user?.id]);

  const login = async (identifier: string, password: string) => {
    const session = await authApi.login(identifier, password);
    await storeSession(session);
    await activate(session);
  };

  const changePassword = async (currentPassword: string, newPassword: string) => {
    const session = await authApi.changePassword(currentPassword, newPassword);
    await storeSession(session);
    await activate(session);
  };

  const selectBusiness = async (id: string) => {
    const selected = businesses.find((business) => business.id === id);
    if (!selected) throw new Error("Business access is unavailable");
    setActiveBusinessState(selected);
    setActiveBusinessHeader(selected.id);
    await storeActiveBusiness(selected.id);
  };

  const logout = async () => {
    await unregisterPushNotifications();
    const refresh = await getRefreshToken();
    if (refresh) {
      try {
        await authApi.logout(refresh);
      } catch {
        // Local credentials are always cleared, even when the server is unreachable.
      } finally {
        await clearSession();
      }
    } else {
      await clearSession();
    }
    setActiveBusinessHeader(null);
    setUser(null);
    setBusinesses([]);
    setActiveBusinessState(null);
    queryClient.clear();
  };

  return (
    <AuthContext.Provider value={{ ready, user, businesses, activeBusiness, login, changePassword, selectBusiness, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}