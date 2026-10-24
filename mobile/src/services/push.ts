import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { apiRequest } from "./api";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export async function registerForPushNotifications(): Promise<void> {
  const existing = await Notifications.getPermissionsAsync();
  const permission = existing.granted ? existing : await Notifications.requestPermissionsAsync();
  if (!permission.granted) return;
  const nativeToken = await Notifications.getDevicePushTokenAsync();
  await apiRequest("/notifications/device-token", {
    method: "PUT",
    body: JSON.stringify({ token: nativeToken.data, platform: Platform.OS }),
  });
}

export async function unregisterPushNotifications(): Promise<void> {
  try {
    const nativeToken = await Notifications.getDevicePushTokenAsync();
    await apiRequest("/notifications/device-token", {
      method: "DELETE",
      body: JSON.stringify({ token: nativeToken.data, platform: Platform.OS }),
    });
  } catch {
    return;
  }
}