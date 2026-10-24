import React from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { RefreshCw, WifiOff } from "lucide-react-native";
import { ActionButton } from "./ActionButton";
import { colors, spacing, typography } from "../theme";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return <View style={styles.state}><ActivityIndicator color={colors.forest} /><Text style={styles.caption}>{label}</Text></View>;
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <View style={styles.state}><Text style={styles.title}>{title}</Text><Text style={styles.caption}>{detail}</Text></View>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <View style={styles.error}><WifiOff size={22} color={colors.coral} /><Text style={styles.title}>Could not refresh</Text><Text style={styles.caption}>{message}</Text><ActionButton title="Retry" icon={RefreshCw} variant="secondary" onPress={onRetry} /></View>;
}

const styles = StyleSheet.create({
  state: { minHeight: 180, alignItems: "center", justifyContent: "center", gap: spacing.md },
  error: { alignItems: "center", gap: spacing.md, padding: spacing.xl, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.line, borderRadius: 8 },
  title: { ...typography.heading },
  caption: { ...typography.body, color: colors.muted, textAlign: "center" },
});