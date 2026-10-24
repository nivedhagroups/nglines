import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { colors, spacing, typography } from "../theme";

export function PageTitle({ title, eyebrow, trailing }: { title: string; eyebrow?: string; trailing?: React.ReactNode }) {
  return (
    <View style={styles.row}>
      <View style={styles.text}>
        {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
        <Text style={styles.title}>{title}</Text>
      </View>
      {trailing}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md },
  text: { flex: 1, gap: spacing.xs },
  eyebrow: { color: colors.forest, fontSize: 11, fontWeight: "800" },
  title: { ...typography.title, fontSize: 26 },
});