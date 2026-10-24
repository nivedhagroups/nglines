import React, { useState } from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Flag } from "lucide-react-native";
import { ActionButton } from "./ActionButton";
import { FormField } from "./FormField";
import { apiRequest, ApiError } from "../services/api";
import { useAuth } from "../state/AuthContext";
import { colors, spacing, typography } from "../theme";

export function FlagAction({ entityType, entityId }: { entityType: "invoice" | "expense"; entityId: string }) {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const allowed = auth.user?.organization_role === "ceo" || auth.user?.organization_role === "super_admin";
  const [visible, setVisible] = useState(false);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => apiRequest("/flags", { method: "POST", body: JSON.stringify({ entity_type: entityType, entity_id: entityId, reason: reason.trim() || undefined }) }),
    onSuccess: async () => {
      setVisible(false);
      setReason("");
      await queryClient.invalidateQueries({ queryKey: ["flags", auth.activeBusiness?.id] });
      await queryClient.invalidateQueries({ queryKey: ["notifications", auth.activeBusiness?.id] });
    },
    onError: (error) => setMessage(error instanceof ApiError ? error.message : "Could not flag transaction"),
  });
  if (!allowed) return null;
  return <>
    <Pressable accessibilityRole="button" accessibilityLabel="Flag transaction as doubtful" style={styles.icon} onPress={() => { setMessage(null); setVisible(true); }}><Flag size={18} color={colors.coral} /></Pressable>
    <Modal visible={visible} transparent animationType="fade" onRequestClose={() => setVisible(false)}>
      <Pressable style={styles.backdrop} onPress={() => setVisible(false)}>
        <View style={styles.modal}>
          <Text style={styles.title}>Flag as doubtful</Text>
          <Text style={styles.detail}>The responsible manager will be notified and must provide a reason or correct the entry.</Text>
          <FormField label="Reason (optional)" value={reason} onChangeText={setReason} multiline />
          {message ? <Text style={styles.error}>{message}</Text> : null}
          <ActionButton title="Send flag" loading={mutation.isPending} onPress={() => mutation.mutate()} />
          <ActionButton title="Cancel" variant="quiet" onPress={() => setVisible(false)} />
        </View>
      </Pressable>
    </Modal>
  </>;
}

const styles = StyleSheet.create({
  icon: { width: 40, height: 40, borderRadius: 8, backgroundColor: "#FBECE8", alignItems: "center", justifyContent: "center" },
  backdrop: { flex: 1, justifyContent: "center", padding: spacing.lg, backgroundColor: "#17252299" },
  modal: { gap: spacing.md, padding: spacing.lg, backgroundColor: colors.surface, borderRadius: 8 },
  title: { ...typography.heading },
  detail: { ...typography.body, color: colors.muted },
  error: { color: colors.error },
});