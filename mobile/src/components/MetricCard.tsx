import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { colors, spacing, typography } from "../theme";

export function MetricCard({ label, value, accent, period }: { label: string; value: string; accent: string; period: string }) {
  return (
    <View style={styles.card}>
      <View style={[styles.accent, { backgroundColor: accent }]} />
      <Text style={styles.period}>{period}</Text>
      <Text style={styles.value} numberOfLines={1} adjustsFontSizeToFit>{value}</Text>
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { flex: 1, minHeight: 120, padding: spacing.md, borderRadius: 8, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface, justifyContent: "space-between" },
  accent: { position: "absolute", left: 0, top: 12, bottom: 12, width: 4, borderTopRightRadius: 3, borderBottomRightRadius: 3 },
  period: { ...typography.caption, textTransform: "uppercase", fontWeight: "700" },
  value: { color: colors.ink, fontSize: 20, fontWeight: "800", marginTop: spacing.md },
  label: { ...typography.caption },
});