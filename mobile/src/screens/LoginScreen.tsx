import React, { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, Text, View } from "react-native";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, Controller } from "react-hook-form";
import { z } from "zod";
import { ArrowRight, ShieldCheck } from "lucide-react-native";
import { ActionButton } from "../components/ActionButton";
import { FormField } from "../components/FormField";
import { Screen } from "../components/Screen";
import { useAuth } from "../state/AuthContext";
import { colors, spacing, typography } from "../theme";

const identitySchema = z.object({ identifier: z.string().trim().min(6, "Enter a valid email or phone number") });
const otpSchema = z.object({ code: z.string().regex(/^\d{6}$/, "Enter the 6-digit code") });
type IdentityForm = z.infer<typeof identitySchema>;
type OtpForm = z.infer<typeof otpSchema>;

export function LoginScreen() {
  const auth = useAuth();
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState<number | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const identityForm = useForm<IdentityForm>({ resolver: zodResolver(identitySchema), defaultValues: { identifier: "" } });
  const otpForm = useForm<OtpForm>({ resolver: zodResolver(otpSchema), defaultValues: { code: "" } });

  useEffect(() => {
    if (!expiresAt) return;
    const timer = setInterval(() => setSecondsLeft(Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000))), 1000);
    return () => clearInterval(timer);
  }, [expiresAt]);

  const requestCode = identityForm.handleSubmit(async ({ identifier }) => {
    setBusy(true);
    setSubmitError(null);
    try {
      const result = await auth.requestOtp(identifier);
      setChallengeId(result.challenge_id);
      setExpiresAt(Date.now() + result.expires_in_seconds * 1000);
      setSecondsLeft(result.expires_in_seconds);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Unable to request a code");
    } finally {
      setBusy(false);
    }
  });

  const verifyCode = otpForm.handleSubmit(async ({ code }) => {
    if (!challengeId) return;
    setBusy(true);
    setSubmitError(null);
    try {
      await auth.verifyOtp(challengeId, code);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "The code could not be verified");
      otpForm.setValue("code", "");
    } finally {
      setBusy(false);
    }
  });

  return (
    <Screen contentStyle={styles.container}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.keyboard}>
        <View style={styles.brandMark}><Text style={styles.markText}>NG</Text></View>
        <Text style={styles.eyebrow}>NIVEDHA GROUPS  /  CHAMBER BRICKS</Text>
        <Text style={styles.title}>A clear view of the work.</Text>
        <Text style={styles.subtitle}>Sign in securely with a one-time code.</Text>
        <View style={styles.form}>
          {!challengeId ? (
            <>
              <Controller control={identityForm.control} name="identifier" render={({ field, fieldState }) => <FormField label="Email or phone" placeholder="name@company.com or +91…" autoCapitalize="none" keyboardType="email-address" value={field.value} onChangeText={field.onChange} onBlur={field.onBlur} error={fieldState.error?.message} />} />
              <ActionButton title="Send secure code" icon={ArrowRight} loading={busy} onPress={requestCode} />
            </>
          ) : (
            <>
              <View style={styles.notice}><ShieldCheck size={19} color={colors.forest} /><Text style={styles.noticeText}>Code sent. Expires in {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, "0")}</Text></View>
              <Controller control={otpForm.control} name="code" render={({ field, fieldState }) => <FormField label="6-digit code" placeholder="000000" keyboardType="number-pad" maxLength={6} value={field.value} onChangeText={field.onChange} onBlur={field.onBlur} error={fieldState.error?.message} />} />
              <ActionButton title="Verify and continue" icon={ArrowRight} loading={busy} onPress={verifyCode} />
              <ActionButton title="Use another email or phone" variant="quiet" onPress={() => { setChallengeId(null); setSubmitError(null); otpForm.reset(); }} />
            </>
          )}
          {submitError ? <Text accessibilityRole="alert" style={styles.error}>{submitError}</Text> : null}
        </View>
        <View style={styles.footer}><Text style={styles.footerText}>Secure access  ·  Asia/Kolkata</Text></View>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, justifyContent: "center", paddingTop: spacing.xxl },
  keyboard: { flex: 1, gap: spacing.md },
  brandMark: { width: 54, height: 54, borderRadius: 12, backgroundColor: colors.lime, alignItems: "center", justifyContent: "center", marginBottom: spacing.lg },
  markText: { fontSize: 18, fontWeight: "800", color: colors.forestDark },
  eyebrow: { color: colors.forest, fontSize: 11, fontWeight: "800" },
  title: { ...typography.title, maxWidth: 320, lineHeight: 34 },
  subtitle: { ...typography.body, color: colors.muted, marginBottom: spacing.lg },
  form: { gap: spacing.md, padding: spacing.lg, backgroundColor: colors.surface, borderRadius: 8, borderWidth: 1, borderColor: colors.line },
  notice: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, backgroundColor: "#EDF5E9", borderRadius: 8 },
  noticeText: { color: colors.forestDark, fontWeight: "600", flexShrink: 1 },
  error: { color: colors.error, fontSize: 13 },
  footer: { marginTop: "auto", paddingTop: spacing.xl },
  footerText: { ...typography.caption },
});