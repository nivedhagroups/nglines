import React from "react";
import { StyleSheet, Text, TextInput, View, type TextInputProps } from "react-native";
import { colors, spacing, typography } from "../theme";

type Props = TextInputProps & { label: string; error?: string };

export function FormField({ label, error, ...inputProps }: Props) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        {...inputProps}
        placeholderTextColor={colors.muted}
        style={[styles.input, inputProps.multiline && styles.multiline, error && styles.invalid]}
      />
      {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.xs },
  label: { ...typography.caption, fontWeight: "700", textTransform: "uppercase" },
  input: { minHeight: 50, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface, borderRadius: 8, paddingHorizontal: spacing.md, color: colors.ink, fontSize: 16 },
  multiline: { minHeight: 92, paddingTop: spacing.md, textAlignVertical: "top" },
  invalid: { borderColor: colors.error },
  error: { color: colors.error, fontSize: 12 },
});