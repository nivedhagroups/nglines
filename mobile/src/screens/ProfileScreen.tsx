import React, { useEffect, useState } from "react";
import { Image, StyleSheet, Text, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Camera, Images, Save } from "lucide-react-native";
import { ActionButton } from "../components/ActionButton";
import { FormField } from "../components/FormField";
import { PageTitle } from "../components/PageTitle";
import { Screen } from "../components/Screen";
import { API_BASE, ApiError, apiRequest } from "../services/api";
import { getAccessToken } from "../services/session";
import { useAuth } from "../state/AuthContext";
import { colors, spacing, typography } from "../theme";

const schema = z.object({ name: z.string().trim().min(1, "Name is required"), email: z.union([z.string().email(), z.literal("")]), phone: z.union([z.string().regex(/^(?:\+91)?[6-9][0-9]{9}$/), z.literal("")]) }).refine((value) => Boolean(value.email || value.phone), { path: ["phone"], message: "Keep at least one login contact" });
type Values = z.infer<typeof schema>;

export function ProfileScreen() {
  const auth = useAuth();
  const [feedback, setFeedback] = useState<string | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [pictureVersion, setPictureVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { name: auth.user?.name ?? "", email: auth.user?.email ?? "", phone: auth.user?.phone ?? "" } });

  useEffect(() => {
    void getAccessToken().then(setAccessToken);
  }, [pictureVersion]);

  const save = form.handleSubmit(async (values) => {
    setBusy(true);
    setFeedback(null);
    try {
      await apiRequest("/profile", { method: "PATCH", body: JSON.stringify({ name: values.name, email: values.email || null, phone: values.phone || null }) });
      setFeedback("Profile updated");
    } catch (error) {
      setFeedback(error instanceof ApiError ? error.message : "Could not update profile");
    } finally {
      setBusy(false);
    }
  });

  const uploadPicture = async (asset: ImagePicker.ImagePickerAsset) => {
    const formData = new FormData();
    formData.append("picture", { uri: asset.uri, name: asset.fileName ?? "profile.jpg", type: asset.mimeType ?? "image/jpeg" } as unknown as Blob);
    try {
      await apiRequest("/profile/picture", { method: "POST", body: formData });
      setPictureVersion((version) => version + 1);
      setFeedback("Profile picture updated");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "Could not upload picture");
    }
  };

  const choosePicture = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setFeedback("Photo library permission is required to choose a profile picture.");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], allowsEditing: true, aspect: [1, 1], quality: 0.85 });
    if (result.canceled || !result.assets[0]) return;
    await uploadPicture(result.assets[0]);
  };

  const takePicture = async () => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      setFeedback("Camera permission is required to take a profile picture.");
      return;
    }
    const result = await ImagePicker.launchCameraAsync({ allowsEditing: true, aspect: [1, 1], quality: 0.85 });
    if (!result.canceled && result.assets[0]) await uploadPicture(result.assets[0]);
  };

  return (
    <Screen>
      <PageTitle eyebrow="ACCOUNT" title="Profile" />
      <View style={styles.avatarWrap}>
        {accessToken ? <Image source={{ uri: `${API_BASE}/profile/picture?version=${pictureVersion}`, headers: { Authorization: `Bearer ${accessToken}` } }} style={styles.avatar} /> : <View style={[styles.avatar, styles.avatarFallback]}><Text style={styles.initial}>{auth.user?.name.slice(0, 1).toUpperCase()}</Text></View>}
        <View style={styles.pictureActions}><ActionButton title="Gallery" icon={Images} variant="secondary" onPress={() => void choosePicture()} /><ActionButton title="Camera" icon={Camera} variant="secondary" onPress={() => void takePicture()} /></View>
      </View>
      <Controller control={form.control} name="name" render={({ field, fieldState }) => <FormField label="Name" value={field.value} onChangeText={field.onChange} onBlur={field.onBlur} error={fieldState.error?.message} />} />
      <Controller control={form.control} name="email" render={({ field, fieldState }) => <FormField label="Email" value={field.value} onChangeText={field.onChange} onBlur={field.onBlur} autoCapitalize="none" keyboardType="email-address" error={fieldState.error?.message} />} />
      <Controller control={form.control} name="phone" render={({ field, fieldState }) => <FormField label="Phone" value={field.value} onChangeText={field.onChange} onBlur={field.onBlur} keyboardType="phone-pad" error={fieldState.error?.message} />} />
      <View style={styles.readonly}><Text style={styles.label}>ROLE</Text><Text style={styles.role}>{auth.activeBusiness?.role.replaceAll("_", " ") ?? "—"}</Text></View>
      {feedback ? <Text accessibilityRole="alert" style={styles.feedback}>{feedback}</Text> : null}
      <ActionButton title="Save changes" icon={Save} loading={busy} onPress={save} />
      <ActionButton title="Sign out" variant="quiet" onPress={() => void auth.logout()} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  avatarWrap: { alignItems: "center", gap: spacing.md },
  avatar: { width: 92, height: 92, borderRadius: 46, backgroundColor: colors.line },
  avatarFallback: { alignItems: "center", justifyContent: "center", backgroundColor: colors.lime },
  pictureActions: { flexDirection: "row", gap: spacing.sm },
  initial: { color: colors.forestDark, fontSize: 32, fontWeight: "800" },
  readonly: { gap: spacing.xs, borderTopWidth: 1, borderTopColor: colors.line, paddingTop: spacing.md },
  label: { ...typography.caption, fontWeight: "700" },
  role: { ...typography.body, textTransform: "capitalize" },
  feedback: { color: colors.forest, fontSize: 13 },
});