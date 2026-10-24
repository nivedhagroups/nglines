import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { FlagAction } from "../components/FlagAction";
import { Pencil } from "lucide-react-native";
import { EmptyState, ErrorState, LoadingState } from "../components/QueryState";
import { PageTitle } from "../components/PageTitle";
import { Screen } from "../components/Screen";
import { resources } from "../services/resources";
import type { RootStackParamList } from "../navigation/types";
import { useAuth } from "../state/AuthContext";
import { colors, spacing, typography } from "../theme";

type Props = NativeStackScreenProps<RootStackParamList, "InvoiceDetail">;

export function InvoiceDetailScreen({ route }: Props) {
  const auth = useAuth();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const query = useQuery({ queryKey: ["invoice", route.params.invoiceId], queryFn: () => resources.invoice(route.params.invoiceId) });
  const invoice = query.data;
  return (
    <Screen>
      {query.isPending ? <LoadingState /> : query.isError ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()} /> : !invoice ? <EmptyState title="Invoice unavailable" detail="This invoice may have been removed or is outside your business." /> : <>
        <PageTitle eyebrow={String(invoice.invoice_date ?? "")} title={String(invoice.invoice_number ?? "Invoice")} trailing={<View style={styles.titleActions}>{auth.activeBusiness?.role ? <Pressable accessibilityRole="button" accessibilityLabel="Correct invoice" style={styles.edit} onPress={() => navigation.navigate("EditInvoice", { invoiceId: route.params.invoiceId })}><Pencil size={18} color={colors.forest} /></Pressable> : null}<FlagAction entityType="invoice" entityId={route.params.invoiceId} /></View>} />
        <View style={styles.summary}><Text style={styles.customer}>{String(invoice.customer_name ?? "Customer")}</Text><Text style={styles.amount}>{new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(invoice.total_amount ?? 0))}</Text><Text style={styles.meta}>{String(invoice.status ?? "").toUpperCase()}</Text></View>
        <Text style={styles.section}>Line items</Text>
        {Array.isArray(invoice.items) ? invoice.items.map((item, index) => {
          const line = item as Record<string, unknown>;
          return <View key={String(line.brick_type_id ?? index)} style={styles.line}><View style={styles.lineInfo}><Text style={styles.customer}>{String(line.description ?? "Brick")}</Text><Text style={styles.meta}>{String(line.quantity)} × ₹{String(line.unit_rate)}</Text></View><Text style={styles.lineTotal}>₹{String(line.line_total)}</Text></View>;
        }) : null}
        <View style={styles.totalRow}><Text style={styles.customer}>Total</Text><Text style={styles.amount}>₹{String(invoice.total_amount ?? "0")}</Text></View>
      </>}
    </Screen>
  );
}

const styles = StyleSheet.create({
  titleActions: { flexDirection: "row", gap: spacing.xs },
  edit: { width: 40, height: 40, borderRadius: 8, backgroundColor: "#E8F1EB", alignItems: "center", justifyContent: "center" },
  summary: { padding: spacing.lg, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.line, borderRadius: 8, gap: spacing.sm },
  customer: { ...typography.body, fontWeight: "700" },
  amount: { color: colors.forestDark, fontSize: 24, fontWeight: "800" },
  meta: { ...typography.caption },
  section: { ...typography.heading, marginTop: spacing.md },
  line: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.line, gap: spacing.md },
  lineInfo: { flex: 1, gap: spacing.xs },
  lineTotal: { ...typography.body, fontWeight: "700" },
  totalRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingTop: spacing.md },
});