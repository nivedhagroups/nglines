import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Plus, Fuel, Wallet } from "lucide-react-native";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { ActionButton } from "../components/ActionButton";
import { EmptyState, ErrorState, LoadingState } from "../components/QueryState";
import { PageTitle } from "../components/PageTitle";
import { Screen } from "../components/Screen";
import { resources } from "../services/resources";
import { useAuth } from "../state/AuthContext";
import type { RootStackParamList } from "../navigation/types";
import { colors, spacing, typography } from "../theme";
import { FlagAction } from "../components/FlagAction";

const money = (value: string) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value));

export function ExpenseListScreen() {
  const auth = useAuth();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const query = useInfiniteQuery({ queryKey: ["expenses", auth.activeBusiness?.id], queryFn: ({ pageParam }) => resources.expenses(pageParam), initialPageParam: undefined as string | undefined, getNextPageParam: (lastPage) => lastPage.page.next_cursor ?? undefined, enabled: Boolean(auth.activeBusiness) });
  const expenses = query.data?.pages.flatMap((page) => page.data) ?? [];
  return (
    <Screen>
      <PageTitle eyebrow="ACCOUNT MANAGEMENT" title="Expenses" trailing={<Pressable accessibilityRole="button" accessibilityLabel="Record expense" style={styles.add} onPress={() => navigation.navigate("CreateExpense")}><Plus size={20} color={colors.surface} /></Pressable>} />
      {query.isPending ? <LoadingState label="Loading expenses" /> : query.isError ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()} /> : !expenses.length ? <EmptyState title="No expenses recorded" detail="Daily costs, diesel, salaries and advances will show here." /> : expenses.map((expense) => (
        <View key={expense.id} style={styles.row}>
          <View style={[styles.icon, expense.expense_type === "diesel" ? styles.fuel : styles.other]}>{expense.expense_type === "diesel" ? <Fuel size={18} color={colors.amber} /> : <Wallet size={18} color={colors.sky} />}</View>
          <Pressable style={styles.info} accessibilityRole="button" onPress={() => navigation.navigate("ExpenseDetail", { expenseId: expense.id })}><Text style={styles.name}>{expense.expense_type.replaceAll("_", " ")}</Text><Text style={styles.meta}>{expense.expense_date}  ·  {expense.description ?? "No description"}</Text></Pressable>
          <View style={styles.trailing}><Text style={styles.total}>{money(expense.amount)}</Text><FlagAction entityType="expense" entityId={expense.id} /></View>
        </View>
      ))}
      {query.hasNextPage ? <ActionButton title={query.isFetchingNextPage ? "Loading" : "Load more"} variant="secondary" loading={query.isFetchingNextPage} onPress={() => void query.fetchNextPage()} /> : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  add: { width: 44, height: 44, borderRadius: 8, backgroundColor: colors.forest, alignItems: "center", justifyContent: "center" },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.line },
  icon: { width: 42, height: 42, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  fuel: { backgroundColor: "#FFF2DC" },
  other: { backgroundColor: "#E8F1F3" },
  info: { flex: 1, gap: 4 },
  name: { ...typography.body, fontWeight: "700", textTransform: "capitalize" },
  meta: { ...typography.caption },
  total: { color: colors.ink, fontWeight: "700" },
  trailing: { alignItems: "flex-end", gap: spacing.xs },
});