import React, { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { EmptyState, ErrorState, LoadingState } from "../components/QueryState";
import { PageTitle } from "../components/PageTitle";
import { FormField } from "../components/FormField";
import { Screen } from "../components/Screen";
import { resources } from "../services/resources";
import type { RootStackParamList } from "../navigation/types";
import { colors, spacing, typography } from "../theme";

type Props = NativeStackScreenProps<RootStackParamList, "CustomerDetail">;

export function CustomerDetailScreen({ route }: Props) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const query = useQuery({ queryKey: ["customer", route.params.customerId, from, to], queryFn: () => resources.customer(route.params.customerId, from || undefined, to || undefined) });
  const customer = query.data?.customer as Record<string, unknown> | undefined;
  const invoices = query.data?.invoices as Record<string, unknown>[] | undefined;
  return (
    <Screen>
      {query.isPending ? <LoadingState /> : query.isError ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()} /> : !customer ? <EmptyState title="Customer unavailable" detail="This customer may have been removed or is outside your business." /> : <>
        <PageTitle eyebrow="CUSTOMER" title={String(customer.name)} />
        <View style={styles.summary}><Text style={styles.phone}>{String(customer.mobile)}</Text><Text style={styles.meta}>{String(customer.gstin ?? "No GSTIN")}</Text><Text style={styles.amount}>{new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(query.data?.purchase_total ?? 0))}</Text><Text style={styles.meta}>Total purchases</Text></View>
        <Text style={styles.heading}>Purchase history</Text>
        <View style={styles.filters}><View style={styles.filter}><FormField label="From" placeholder="YYYY-MM-DD" value={from} onChangeText={setFrom} /></View><View style={styles.filter}><FormField label="To" placeholder="YYYY-MM-DD" value={to} onChangeText={setTo} /></View></View>
        {!invoices?.length ? <EmptyState title="No purchases yet" detail="Invoices for this customer will appear here." /> : invoices.map((invoice) => <View key={String(invoice.id)} style={styles.row}><View><Text style={styles.invoice}>{String(invoice.invoice_number)}</Text><Text style={styles.meta}>{String(invoice.invoice_date)}</Text></View><Text style={styles.invoice}>₹{String(invoice.total_amount)}</Text></View>)}
      </>}
    </Screen>
  );
}

const styles = StyleSheet.create({
  summary: { padding: spacing.lg, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.line, borderRadius: 8, gap: spacing.sm },
  phone: { ...typography.body },
  amount: { color: colors.forestDark, fontSize: 24, fontWeight: "800", marginTop: spacing.md },
  meta: { ...typography.caption },
  heading: { ...typography.heading },
  filters: { flexDirection: "row", gap: spacing.md },
  filter: { flex: 1 },
  row: { flexDirection: "row", justifyContent: "space-between", paddingVertical: spacing.md, borderBottomWidth: 1, borderColor: colors.line },
  invoice: { ...typography.body, fontWeight: "700" },
});