import React from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import type { LucideIcon } from "lucide-react-native";
import { colors, spacing } from "../theme";

type Props = {
  title: string;
  onPress: () => void;
  icon?: LucideIcon;
  variant?: "primary" | "secondary" | "quiet" | "danger";
  disabled?: boolean;
  loading?: boolean;
};

export function ActionButton({ title, onPress, icon: Icon, variant = "primary", disabled, loading }: Props) {
  const tone = variant === "primary" ? colors.forest : variant === "danger" ? colors.coral : colors.surface;
  const textColor = variant === "primary" || variant === "danger" ? colors.surface : colors.ink;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      disabled={disabled || loading}
      onPress={onPress}
      style={({ pressed }) => [styles.button, styles[variant], { opacity: pressed ? 0.82 : disabled ? 0.5 : 1 }]}
    >
      {loading ? <ActivityIndicator color={textColor} /> : <View style={styles.row}>{Icon ? <Icon size={18} color={textColor} /> : null}<Text style={[styles.label, { color: textColor }]}>{title}</Text></View>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: { minHeight: 50, paddingHorizontal: spacing.lg, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  primary: { backgroundColor: colors.forest },
  secondary: { backgroundColor: colors.surface, borderColor: colors.line, borderWidth: 1 },
  quiet: { backgroundColor: "transparent" },
  danger: { backgroundColor: colors.coral },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  label: { fontSize: 15, fontWeight: "700" },
});