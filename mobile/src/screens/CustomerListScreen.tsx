import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { Search, UserRound } from "lucide-react-native";
import { FormField } from "../components/FormField";
import { ActionButton } from "../components/ActionButton";
import { EmptyState, ErrorState, LoadingState } from "../components/QueryState";
import { PageTitle } from "../components/PageTitle";
import { Screen } from "../components/Screen";
import { resources } from "../services/resources";
import { useAuth } from "../state/AuthContext";
import type { RootStackParamList } from "../navigation/types";
import { colors, spacing, typography } from "../theme";

export function CustomerListScreen() {
  const auth = useAuth();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [search, setSearch] = useState("");
  const query = useInfiniteQuery({ queryKey: ["customers", auth.activeBusiness?.id, search], queryFn: ({ pageParam }) => resources.customers(search, pageParam), initialPageParam: undefined as string | undefined, getNextPageParam: (lastPage) => lastPage.page.next_cursor ?? undefined, enabled: Boolean(auth.activeBusiness) });
  const customers = query.data?.pages.flatMap((page) => page.data) ?? [];
  return (
    <Screen>
      <PageTitle eyebrow="CHAMBER BRICKS" title="Customers" />
      <FormField label="Search customers" placeholder="Name, mobile or GSTIN" value={search} onChangeText={setSearch} autoCapitalize="none" />
      {query.isPending ? <LoadingState label="Loading customers" /> : query.isError ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()} /> : !customers.length ? <EmptyState title="No matching customers" detail="Customers saved from invoices appear here automatically." /> : customers.map((customer) => (
        <Pressable key={customer.id} style={styles.row} accessibilityRole="button" onPress={() => navigation.navigate("CustomerDetail", { customerId: customer.id })}>
          <View style={styles.avatar}><UserRound size={18} color={colors.forest} /></View>
          <View style={styles.info}><Text style={styles.name}>{customer.name}</Text><Text style={styles.meta}>{customer.mobile}{customer.location ? `  ·  ${customer.location}` : ""}</Text></View>
          <Search size={17} color={colors.muted} />
        </Pressable>
      ))}
      {query.hasNextPage ? <ActionButton title={query.isFetchingNextPage ? "Loading" : "Load more customers"} variant="secondary" loading={query.isFetchingNextPage} onPress={() => void query.fetchNextPage()} /> : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.line },
  avatar: { width: 42, height: 42, borderRadius: 8, backgroundColor: "#E8F1EB", alignItems: "center", justifyContent: "center" },
  info: { flex: 1, gap: 4 },
  name: { ...typography.body, fontWeight: "700" },
  meta: { ...typography.caption },
});