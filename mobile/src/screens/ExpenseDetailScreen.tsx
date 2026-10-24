import React, { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { Save } from "lucide-react-native";
import { ActionButton } from "../components/ActionButton";
import { FlagAction } from "../components/FlagAction";
import { FormField } from "../components/FormField";
import { ErrorState, LoadingState } from "../components/QueryState";
import { PageTitle } from "../components/PageTitle";
import { Screen } from "../components/Screen";
import { resources } from "../services/resources";
import { useAuth } from "../state/AuthContext";
import type { RootStackParamList } from "../navigation/types";
import { colors, spacing, typography } from "../theme";

const schema = z.object({ amount: z.string().regex(/^\d+(\.\d{1,2})?$/, "Enter a valid amount"), description: z.string().optional(), litres: z.string().optional(), unit_rate: z.string().optional() });
type Values = z.infer<typeof schema>;
type Props = NativeStackScreenProps<RootStackParamList, "ExpenseDetail">;

function dieselTotal(litres: string, rate: string): string | null {
  if (!/^\d+(\.\d{1,3})?$/.test(litres) || !/^\d+(\.\d{1,2})?$/.test(rate)) return null;
  const litreParts = litres.split(".");
  const rateParts = rate.split(".");
  const milliLitres = BigInt(litreParts[0]) * 1000n + BigInt((litreParts[1] ?? "").padEnd(3, "0"));
  const ratePaise = BigInt(rateParts[0]) * 100n + BigInt((rateParts[1] ?? "").padEnd(2, "0"));
  const paise = (milliLitres * ratePaise + 500n) / 1000n;
  return `${paise / 100n}.${String(paise % 100n).padStart(2, "0")}`;
}

export function ExpenseDetailScreen({ route }: Props) {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["expense", route.params.expenseId], queryFn: () => resources.expense(route.params.expenseId) });
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { amount: "", description: "", litres: "", unit_rate: "" } });
  const values = useWatch({ control: form.control });
  const isDiesel = query.data?.expense_type === "diesel";
  const total = isDiesel ? dieselTotal(values.litres ?? "", values.unit_rate ?? "") : null;

  useEffect(() => {
    if (!query.data) return;
    form.reset({ amount: String(query.data.amount ?? ""), description: String(query.data.description ?? ""), litres: String(query.data.litres ?? ""), unit_rate: String(query.data.unit_rate ?? "") });
  }, [form, query.data]);

  const update = useMutation({
    mutationFn: (body: Values) => resources.updateExpense(route.params.expenseId, { amount: isDiesel ? total : body.amount, description: body.description || null, ...(isDiesel ? { litres: body.litres, unit_rate: body.unit_rate } : {}) }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["expense", route.params.expenseId] });
      await queryClient.invalidateQueries({ queryKey: ["expenses", auth.activeBusiness?.id] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard", auth.activeBusiness?.id] });
    },
  });

  return (
    <Screen>
      {query.isPending ? <LoadingState /> : query.isError ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()} /> : !query.data ? null : <>
        <PageTitle eyebrow={String(query.data.expense_date)} title={String(query.data.expense_type).replaceAll("_", " ")} trailing={<FlagAction entityType="expense" entityId={route.params.expenseId} />} />
        <View style={styles.summary}><Text style={styles.amount}>₹{String(query.data.amount)}</Text><Text style={styles.meta}>Responsible manager: {String(query.data.responsible_user_id ?? "Not assigned")}</Text></View>
        <Text style={styles.heading}>Correct entry</Text>
        {isDiesel ? <>
          <View style={styles.pair}><View style={styles.flex}><Controller control={form.control} name="litres" render={({ field, fieldState }) => <FormField label="Litres" keyboardType="decimal-pad" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} /></View><View style={styles.flex}><Controller control={form.control} name="unit_rate" render={({ field, fieldState }) => <FormField label="Rate per litre" keyboardType="decimal-pad" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} /></View></View>
          <FormField label="Calculated amount" value={total ?? ""} editable={false} />
        </> : <Controller control={form.control} name="amount" render={({ field, fieldState }) => <FormField label="Amount (INR)" keyboardType="decimal-pad" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} />}
        <Controller control={form.control} name="description" render={({ field }) => <FormField label="Description" multiline value={field.value} onChangeText={field.onChange} />} />
        <ActionButton title="Save correction" icon={Save} loading={update.isPending} onPress={form.handleSubmit((body) => update.mutate(body))} />
        {update.isError ? <Text style={styles.error}>{update.error.message}</Text> : null}
        <Text style={styles.heading}>Bill attachments</Text>
        {Array.isArray(query.data.attachments) && query.data.attachments.length ? (query.data.attachments as Record<string, unknown>[]).map((file) => <View key={String(file.id)} style={styles.attachment}><Text style={styles.meta}>{String(file.filename)}  ·  {String(file.content_type)}</Text></View>) : <Text style={styles.meta}>No bill attached.</Text>}
      </>}
    </Screen>
  );
}

const styles = StyleSheet.create({
  summary: { padding: spacing.md, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.line, borderRadius: 8, gap: spacing.sm },
  amount: { color: colors.forestDark, fontSize: 24, fontWeight: "800" },
  meta: { ...typography.caption },
  heading: { ...typography.heading, marginTop: spacing.sm },
  pair: { flexDirection: "row", gap: spacing.md },
  flex: { flex: 1 },
  attachment: { paddingVertical: spacing.md, borderBottomWidth: 1, borderColor: colors.line },
  error: { color: colors.error },
});