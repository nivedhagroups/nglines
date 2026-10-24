import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useNavigation } from "@react-navigation/native";
import { Plus, ReceiptText } from "lucide-react-native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { ActionButton } from "../components/ActionButton";
import { EmptyState, ErrorState, LoadingState } from "../components/QueryState";
import { PageTitle } from "../components/PageTitle";
import { Screen } from "../components/Screen";
import { resources } from "../services/resources";
import { useAuth } from "../state/AuthContext";
import type { RootStackParamList } from "../navigation/types";
import { colors, spacing, typography } from "../theme";

const money = (value: string) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value));

export function InvoiceListScreen() {
  const auth = useAuth();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const query = useInfiniteQuery({ queryKey: ["invoices", auth.activeBusiness?.id], queryFn: ({ pageParam }) => resources.invoices(pageParam), initialPageParam: undefined as string | undefined, getNextPageParam: (lastPage) => lastPage.page.next_cursor ?? undefined, enabled: Boolean(auth.activeBusiness) });
  const invoices = query.data?.pages.flatMap((page) => page.data) ?? [];
  return (
    <Screen>
      <PageTitle eyebrow="SALES" title="Invoices" trailing={<Pressable accessibilityRole="button" accessibilityLabel="Create invoice" style={styles.add} onPress={() => navigation.navigate("CreateInvoice")}><Plus size={20} color={colors.surface} /></Pressable>} />
      {query.isPending ? <LoadingState label="Loading invoices" /> : query.isError ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()} /> : !invoices.length ? <EmptyState title="No invoices yet" detail="Issued invoices will appear here." /> : invoices.map((invoice) => (
        <Pressable key={invoice.id} accessibilityRole="button" style={styles.row} onPress={() => navigation.navigate("InvoiceDetail", { invoiceId: invoice.id })}>
          <View style={styles.icon}><ReceiptText size={19} color={colors.forest} /></View>
          <View style={styles.info}><Text style={styles.name}>{invoice.customer_name}</Text><Text style={styles.meta}>{invoice.invoice_number}  ·  {invoice.invoice_date}</Text></View>
          <View style={styles.amount}><Text style={styles.total}>{money(invoice.total_amount)}</Text><Text style={styles.meta}>{invoice.status}</Text></View>
        </Pressable>
      ))}
      {query.hasNextPage ? <ActionButton title={query.isFetchingNextPage ? "Loading" : "Load more"} variant="secondary" loading={query.isFetchingNextPage} onPress={() => void query.fetchNextPage()} /> : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  add: { width: 44, height: 44, borderRadius: 8, backgroundColor: colors.forest, alignItems: "center", justifyContent: "center" },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.line },
  icon: { width: 42, height: 42, borderRadius: 8, backgroundColor: "#E8F1EB", alignItems: "center", justifyContent: "center" },
  info: { flex: 1, gap: 4 },
  name: { ...typography.body, fontWeight: "700" },
  meta: { ...typography.caption },
  amount: { alignItems: "flex-end", gap: 4 },
  total: { color: colors.ink, fontWeight: "700" },
});