import React, { useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, Text, View } from "react-native";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, Controller } from "react-hook-form";
import { z } from "zod";
import { ArrowRight } from "lucide-react-native";
import { ActionButton } from "../components/ActionButton";
import { FormField } from "../components/FormField";
import { Screen } from "../components/Screen";
import { useAuth } from "../state/AuthContext";
import { colors, spacing, typography } from "../theme";

const schema = z.object({
  identifier: z.string().trim().min(3, "Enter your email or phone number"),
  password: z.string().min(1, "Enter your password"),
});
type Values = z.infer<typeof schema>;

export function LoginScreen() {
  const auth = useAuth();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { identifier: "", password: "" } });

  const submit = form.handleSubmit(async ({ identifier, password }) => {
    setBusy(true);
    setSubmitError(null);
    try {
      await auth.login(identifier, password);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Unable to sign in");
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
        <Text style={styles.subtitle}>Sign in with your email or phone and password.</Text>
        <View style={styles.form}>
          <Controller control={form.control} name="identifier" render={({ field, fieldState }) => <FormField label="Email or phone" placeholder="name@company.com or +91…" autoCapitalize="none" autoCorrect={false} value={field.value} onChangeText={field.onChange} onBlur={field.onBlur} error={fieldState.error?.message} />} />
          <Controller control={form.control} name="password" render={({ field, fieldState }) => <FormField label="Password" placeholder="Enter your password" secureTextEntry autoCapitalize="none" value={field.value} onChangeText={field.onChange} onBlur={field.onBlur} error={fieldState.error?.message} />} />
          <ActionButton title="Sign in" icon={ArrowRight} loading={busy} onPress={submit} />
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
  error: { color: colors.error, fontSize: 13 },
  footer: { marginTop: "auto", paddingTop: spacing.xl },
  footerText: { ...typography.caption },
});