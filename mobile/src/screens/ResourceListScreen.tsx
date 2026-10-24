import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { Plus } from "lucide-react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { EmptyState, ErrorState, LoadingState } from "../components/QueryState";
import { PageTitle } from "../components/PageTitle";
import { Screen } from "../components/Screen";
import { resources } from "../services/resources";
import { useAuth } from "../state/AuthContext";
import type { RootStackParamList } from "../navigation/types";
import { colors, spacing, typography } from "../theme";
import { ActionButton } from "../components/ActionButton";
import { FormField } from "../components/FormField";

type Props = NativeStackScreenProps<RootStackParamList, "ResourceList">;
type Row = Record<string, unknown>;

const titles = { settings: "Business settings", users: "Users", audit: "Audit log", notifications: "Notifications", estimates: "Estimates", flags: "Doubtful transactions" } as const;

export function ResourceListScreen({ route }: Props) {
  const auth = useAuth();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const queryClient = useQueryClient();
  const { resource } = route.params;
  const query = useQuery({
    queryKey: [resource, auth.activeBusiness?.id],
    queryFn: async () => {
      if (resource === "settings") return resources.businessSettings();
      if (resource === "users") return resources.users();
      if (resource === "audit") return resources.auditLogs();
      if (resource === "notifications") return resources.notifications();
      if (resource === "flags") return resources.flags();
      return resources.estimates();
    },
    enabled: Boolean(auth.activeBusiness),
  });

  const data = query.data;
  let rows: Row[] = [];
  if (data && "data" in data && Array.isArray(data.data)) rows = data.data as Row[];
  if (data && !Array.isArray(data) && !("data" in data)) rows = [data as Row];

  const convertMutation = useMutation({
    mutationFn: (estimateId: string) => resources.convertEstimate(estimateId, new Date().toISOString().slice(0, 10), `convert-${estimateId}-${Date.now()}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["estimates", auth.activeBusiness?.id] });
      await queryClient.invalidateQueries({ queryKey: ["invoices", auth.activeBusiness?.id] });
    },
  });

  return (
    <Screen>
      <PageTitle eyebrow={auth.activeBusiness?.name.toUpperCase()} title={titles[resource]} trailing={resource === "estimates" ? <Pressable accessibilityRole="button" accessibilityLabel="Create estimate" style={styles.add} onPress={() => navigation.navigate("CreateEstimate")}><Plus size={20} color={colors.surface} /></Pressable> : null} />
      {query.isPending ? <LoadingState /> : query.isError ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()} /> : !rows.length ? <EmptyState title="Nothing to show" detail="Records will appear here when available." /> : rows.map((row, index) => (
        <View key={String(row.id ?? row.key ?? index)} style={styles.row}>
          <Text style={styles.primary}>{String(row.name ?? row.title ?? row.invoice_number ?? row.estimate_number ?? row.action ?? row.legal_name ?? row.id ?? "Record")}</Text>
          <Text style={styles.secondary}>{String(row.status ?? row.role ?? row.occurred_at ?? row.created_at ?? row.display_name ?? "")}</Text>
          {row.message ? <Text style={styles.secondary}>{String(row.message)}</Text> : null}
          {resource === "estimates" && !row.converted_invoice_id ? <ActionButton title="Convert to invoice" loading={convertMutation.isPending} variant="secondary" onPress={() => convertMutation.mutate(String(row.id))} /> : null}
          {resource === "flags" ? <FlagRecordActions row={row} businessId={auth.activeBusiness?.id ?? ""} role={auth.activeBusiness?.role ?? "manager"} /> : null}
        </View>
      ))}
    </Screen>
  );
}

function FlagRecordActions({ row, businessId, role }: { row: Row; businessId: string; role: string }) {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const queryClient = useQueryClient();
  const [text, setText] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const id = String(row.id);
  const isManager = role === "manager" || role === "asst_manager";
  const canResolve = role === "ceo" || role === "super_admin";
  const status = String(row.status);
  const response = useMutation({ mutationFn: () => resources.flagResponse(id, text), onSuccess: async () => { setText(""); await queryClient.invalidateQueries({ queryKey: ["flags", businessId] }); }, onError: (reason) => setError(reason instanceof Error ? reason.message : "Could not submit response") });
  const corrected = useMutation({ mutationFn: () => resources.flagCorrected(id, text), onSuccess: async () => { setText(""); await queryClient.invalidateQueries({ queryKey: ["flags", businessId] }); }, onError: (reason) => setError(reason instanceof Error ? reason.message : "Could not mark corrected") });
  const resolve = useMutation({ mutationFn: () => resources.resolveFlag(id, text), onSuccess: async () => { setText(""); await queryClient.invalidateQueries({ queryKey: ["flags", businessId] }); }, onError: (reason) => setError(reason instanceof Error ? reason.message : "Could not resolve flag") });
  const reflag = useMutation({ mutationFn: () => resources.reflag(id, text), onSuccess: async () => { setText(""); await queryClient.invalidateQueries({ queryKey: ["flags", businessId] }); }, onError: (reason) => setError(reason instanceof Error ? reason.message : "Could not re-flag transaction") });
  return <View style={styles.flagActions}>
    <ActionButton title="Open transaction" variant="quiet" onPress={() => row.entity_type === "invoice" ? navigation.navigate("InvoiceDetail", { invoiceId: String(row.entity_id) }) : navigation.navigate("ExpenseDetail", { expenseId: String(row.entity_id) })} />
    {isManager && (status === "flagged" || status === "reason_submitted") ? <>
      <FormField label="Reason or correction summary" value={text} onChangeText={setText} multiline />
      <ActionButton title="Submit reason" variant="secondary" loading={response.isPending} disabled={!text.trim()} onPress={() => { setError(null); response.mutate(); }} />
      <ActionButton title="Mark corrected" variant="secondary" loading={corrected.isPending} disabled={!text.trim()} onPress={() => { setError(null); corrected.mutate(); }} />
    </> : null}
    {canResolve && (status === "reason_submitted" || status === "corrected") ? <ActionButton title="Resolve" variant="secondary" loading={resolve.isPending} onPress={() => { setError(null); resolve.mutate(); }} /> : null}
    {canResolve && status === "resolved" ? <><FormField label="Re-flag reason" value={text} onChangeText={setText} multiline /><ActionButton title="Re-flag" variant="secondary" loading={reflag.isPending} disabled={!text.trim()} onPress={() => { setError(null); reflag.mutate(); }} /></> : null}
    {error ? <Text style={styles.error}>{error}</Text> : null}
  </View>;
}

const styles = StyleSheet.create({
  add: { width: 44, height: 44, borderRadius: 8, backgroundColor: colors.forest, alignItems: "center", justifyContent: "center" },
  row: { paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.line, gap: spacing.xs },
  primary: { ...typography.body, fontWeight: "700" },
  secondary: { ...typography.caption },
  flagActions: { gap: spacing.sm, marginTop: spacing.sm },
  error: { color: colors.error, fontSize: 12 },
});