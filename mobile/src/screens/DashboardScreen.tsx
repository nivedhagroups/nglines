import React from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { useNavigation } from "@react-navigation/native";
import { ArrowDownRight, ArrowUpRight, Plus } from "lucide-react-native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { resources } from "../services/resources";
import { useAuth } from "../state/AuthContext";
import type { RootStackParamList } from "../navigation/types";
import { ActionButton } from "../components/ActionButton";
import { EmptyState, ErrorState, LoadingState } from "../components/QueryState";
import { MetricCard } from "../components/MetricCard";
import { PageTitle } from "../components/PageTitle";
import { Screen } from "../components/Screen";
import { colors, spacing, typography } from "../theme";

const periods = [
  ["Annual", "annual", colors.forest],
  ["Monthly", "monthly", colors.sky],
  ["Weekly", "weekly", colors.amber],
  ["Today", "daily", colors.coral],
] as const;

function formatINR(amount?: string): string {
  const value = Number(amount ?? 0);
  if (!Number.isFinite(value)) return "₹—";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value);
}

export function DashboardScreen() {
  const auth = useAuth();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const query = useQuery({ queryKey: ["dashboard", auth.activeBusiness?.id], queryFn: resources.dashboard, enabled: Boolean(auth.activeBusiness) });

  return (
    <Screen scroll={false} contentStyle={styles.screen}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={query.isRefetching} onRefresh={() => void query.refetch()} tintColor={colors.forest} />}
      >
        <PageTitle eyebrow={auth.activeBusiness?.name.toUpperCase()} title="Overview" />
        <View style={styles.periodHeader}><ArrowUpRight size={18} color={colors.forest} /><Text style={styles.sectionTitle}>Sales</Text><Text style={styles.context}>INR</Text></View>
        {query.isPending ? <LoadingState label="Loading sales and expense totals" /> : query.isError ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()} /> : query.data ? (
          <View style={styles.grid}>
            {periods.map(([label, key, accent]) => <MetricCard key={`sales-${key}`} label="Sales" period={label} value={formatINR(query.data.sales[key]?.amount)} accent={accent} />)}
          </View>
        ) : <EmptyState title="No dashboard data" detail="Business totals will appear here." />}

        <View style={[styles.periodHeader, styles.expenseHeading]}><ArrowDownRight size={18} color={colors.coral} /><Text style={styles.sectionTitle}>Expenses</Text><Text style={styles.context}>INR</Text></View>
        {query.data ? <View style={styles.grid}>{periods.map(([label, key, accent]) => <MetricCard key={`expense-${key}`} label="Expenses" period={label} value={formatINR(query.data.expenses[key]?.amount)} accent={accent} />)}</View> : null}

        <View style={styles.actions}>
          <ActionButton title="New invoice" icon={Plus} onPress={() => navigation.navigate("CreateInvoice")} />
          <ActionButton title="Record expense" icon={Plus} variant="secondary" onPress={() => navigation.navigate("CreateExpense")} />
        </View>
        {!auth.activeBusiness ? <Text style={styles.context}>Choose a business to view its activity.</Text> : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, paddingHorizontal: 0, paddingTop: 0, paddingBottom: 0 },
  content: { padding: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.md },
  periodHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.sm },
  expenseHeading: { marginTop: spacing.lg },
  sectionTitle: { ...typography.heading, flex: 1 },
  context: { ...typography.caption },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  actions: { gap: spacing.sm, marginTop: spacing.lg },
});