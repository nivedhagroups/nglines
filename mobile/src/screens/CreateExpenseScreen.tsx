import React, { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { Camera } from "lucide-react-native";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { ActionButton } from "../components/ActionButton";
import { FormField } from "../components/FormField";
import { LoadingState } from "../components/QueryState";
import { PageTitle } from "../components/PageTitle";
import { Screen } from "../components/Screen";
import { ApiError, apiRequest } from "../services/api";
import { resources } from "../services/resources";
import { useAuth } from "../state/AuthContext";
import type { RootStackParamList } from "../navigation/types";
import { colors, spacing, typography } from "../theme";

const expenseTypes = ["daily", "diesel", "salary", "salary_advance", "miscellaneous"] as const;
const schema = z.object({
  expense_type: z.enum(expenseTypes),
  category_id: z.string().min(1, "Select a category"),
  expense_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  amount: z.string().regex(/^\d+(\.\d{1,2})?$/, "Enter a valid amount"),
  description: z.string().optional(),
  vehicle_id: z.string().optional(),
  litres: z.string().optional(),
  unit_rate: z.string().optional(),
  employee_id: z.string().optional(),
  salary_period: z.enum(["daily", "weekly", "monthly"]).optional(),
  recipient_name: z.string().optional(),
  responsible_manager_id: z.string().optional(),
}).superRefine((value, context) => {
  if (value.expense_type === "diesel") {
    if (!value.vehicle_id) context.addIssue({ code: "custom", path: ["vehicle_id"], message: "Select a vehicle" });
    if (!value.litres || Number(value.litres) <= 0) context.addIssue({ code: "custom", path: ["litres"], message: "Enter litres" });
    if (!value.unit_rate || Number(value.unit_rate) < 0) context.addIssue({ code: "custom", path: ["unit_rate"], message: "Enter the per-litre rate" });
  }
  if (value.expense_type === "salary" && !value.salary_period) context.addIssue({ code: "custom", path: ["salary_period"], message: "Choose salary period" });
  if (value.expense_type === "salary_advance" && !value.employee_id && !value.recipient_name?.trim()) context.addIssue({ code: "custom", path: ["recipient_name"], message: "Select a labourer or enter their name" });
});

type FormValues = z.infer<typeof schema>;

function dieselTotal(litres: string, rate: string): string | null {
  if (!litres || !rate || !/^\d+(\.\d{1,3})?$/.test(litres) || !/^\d+(\.\d{1,2})?$/.test(rate)) return null;
  const litreParts = litres.split(".");
  const rateParts = rate.split(".");
  const milliLitres = BigInt(litreParts[0]) * 1000n + BigInt((litreParts[1] ?? "").padEnd(3, "0"));
  const ratePaise = BigInt(rateParts[0]) * 100n + BigInt((rateParts[1] ?? "").padEnd(2, "0"));
  const paise = (milliLitres * ratePaise + 500n) / 1000n;
  return `${paise / 100n}.${String(paise % 100n).padStart(2, "0")}`;
}

export function CreateExpenseScreen() {
  const auth = useAuth();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const queryClient = useQueryClient();
  const [bill, setBill] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const categories = useQuery({ queryKey: ["expense-categories", auth.activeBusiness?.id], queryFn: resources.expenseCategories, enabled: Boolean(auth.activeBusiness) });
  const vehicles = useQuery({ queryKey: ["vehicles", auth.activeBusiness?.id], queryFn: resources.vehicles, enabled: Boolean(auth.activeBusiness) });
  const employees = useQuery({ queryKey: ["employees", auth.activeBusiness?.id], queryFn: resources.employees, enabled: Boolean(auth.activeBusiness) });
  const managers = useQuery({ queryKey: ["responsible-managers", auth.activeBusiness?.id], queryFn: resources.managers, enabled: Boolean(auth.activeBusiness && auth.user?.organization_role) });
  const isGroupRole = Boolean(auth.user?.organization_role);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { expense_type: "daily", category_id: "", expense_date: new Date().toISOString().slice(0, 10), amount: "", description: "", vehicle_id: "", litres: "", unit_rate: "", employee_id: "", recipient_name: "", responsible_manager_id: "" },
  });
  const type = useWatch({ control: form.control, name: "expense_type" });
  const litres = useWatch({ control: form.control, name: "litres" });
  const unitRate = useWatch({ control: form.control, name: "unit_rate" });
  const filteredCategories = categories.data?.data.filter((category) => category.expense_type === type) ?? [];
  const calculatedAmount = type === "diesel" && litres && unitRate ? dieselTotal(litres, unitRate) : null;

  useEffect(() => {
    if (type === "diesel" && calculatedAmount) form.setValue("amount", calculatedAmount, { shouldValidate: true });
  }, [calculatedAmount, form, type]);

  const chooseBill = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setFeedback("Photo library permission is required to attach a bill.");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.85 });
    if (!result.canceled) setBill(result.assets[0] ?? null);
  };

  const mutation = useMutation({
    mutationFn: async (values: FormValues) => {
      const result = await resources.createExpense({
        expense_type: values.expense_type,
        category_id: values.category_id,
        expense_date: values.expense_date,
        amount: values.expense_type === "diesel" ? calculatedAmount ?? values.amount : values.amount,
        description: values.description || undefined,
        vehicle_id: values.vehicle_id || undefined,
        litres: values.expense_type === "diesel" ? values.litres : undefined,
        unit_rate: values.expense_type === "diesel" ? values.unit_rate : undefined,
        employee_id: values.employee_id || undefined,
        salary_period: values.expense_type === "salary" ? values.salary_period : undefined,
        recipient_name: values.recipient_name || undefined,
        responsible_manager_id: isGroupRole ? values.responsible_manager_id : undefined,
      });
      if (bill && result.id) {
        const formData = new FormData();
        formData.append("attachment", { uri: bill.uri, name: bill.fileName ?? "bill.jpg", type: bill.mimeType ?? "image/jpeg" } as unknown as Blob);
        await apiRequest(`/expenses/${String(result.id)}/attachments`, { method: "POST", body: formData });
      }
      return result;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["expenses", auth.activeBusiness?.id] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard", auth.activeBusiness?.id] });
      navigation.goBack();
    },
    onError: (error) => setFeedback(error instanceof ApiError ? error.message : "Unable to save expense"),
  });

  const submit = form.handleSubmit((values) => {
    setFeedback(null);
    if (isGroupRole && !values.responsible_manager_id) {
      setFeedback("Select the responsible Manager or Asst Manager.");
      return;
    }
    mutation.mutate(values);
  });

  return (
    <Screen>
      <PageTitle eyebrow="ACCOUNT MANAGEMENT" title="Record expense" />
      <Text style={styles.label}>EXPENSE TYPE</Text>
      <View style={styles.types}>{expenseTypes.map((item) => <Pressable key={item} style={[styles.typeButton, type === item && styles.typeActive]} onPress={() => { form.setValue("expense_type", item, { shouldValidate: true }); form.setValue("category_id", ""); }}><Text style={[styles.typeText, type === item && styles.typeTextActive]}>{item.replaceAll("_", " ")}</Text></Pressable>)}</View>
      <Text style={styles.label}>CATEGORY</Text>
      {categories.isPending ? <LoadingState label="Loading categories" /> : <View style={styles.types}>{filteredCategories.map((category) => <Pressable key={category.id} style={[styles.typeButton, form.watch("category_id") === category.id && styles.typeActive]} onPress={() => form.setValue("category_id", category.id, { shouldValidate: true })}><Text style={[styles.typeText, form.watch("category_id") === category.id && styles.typeTextActive]}>{category.name}</Text></Pressable>)}</View>}
      {form.formState.errors.category_id ? <Text style={styles.error}>{form.formState.errors.category_id.message}</Text> : null}
      <Controller control={form.control} name="expense_date" render={({ field, fieldState }) => <FormField label="Date" placeholder="YYYY-MM-DD" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} />

      {type === "diesel" ? <>
        <Text style={styles.label}>VEHICLE</Text>
        {vehicles.isPending ? <LoadingState label="Loading vehicles" /> : <View style={styles.types}>{vehicles.data?.data.map((vehicle) => <Pressable key={vehicle.id} style={[styles.typeButton, form.watch("vehicle_id") === vehicle.id && styles.typeActive]} onPress={() => form.setValue("vehicle_id", vehicle.id, { shouldValidate: true })}><Text style={[styles.typeText, form.watch("vehicle_id") === vehicle.id && styles.typeTextActive]}>{vehicle.registration_number}</Text></Pressable>)}</View>}
        {form.formState.errors.vehicle_id ? <Text style={styles.error}>{form.formState.errors.vehicle_id.message}</Text> : null}
        <View style={styles.twoFields}>
          <View style={styles.flex}><Controller control={form.control} name="litres" render={({ field, fieldState }) => <FormField label="Litres" keyboardType="decimal-pad" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} /></View>
          <View style={styles.flex}><Controller control={form.control} name="unit_rate" render={({ field, fieldState }) => <FormField label="Rate per litre" keyboardType="decimal-pad" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} /></View>
        </View>
      </> : null}

      {type === "salary" ? <View style={styles.field}><Text style={styles.label}>SALARY PERIOD</Text><View style={styles.types}>{(["daily", "weekly", "monthly"] as const).map((period) => <Pressable key={period} style={[styles.typeButton, form.watch("salary_period") === period && styles.typeActive]} onPress={() => form.setValue("salary_period", period)}><Text style={[styles.typeText, form.watch("salary_period") === period && styles.typeTextActive]}>{period}</Text></Pressable>)}</View></View> : null}

      {type === "salary_advance" ? <>
        <Text style={styles.label}>LABOURER (OPTIONAL)</Text>
        <View style={styles.types}>{employees.data?.data.map((employee) => <Pressable key={employee.id} style={[styles.typeButton, form.watch("employee_id") === employee.id && styles.typeActive]} onPress={() => { form.setValue("employee_id", employee.id); form.setValue("recipient_name", ""); }}><Text style={[styles.typeText, form.watch("employee_id") === employee.id && styles.typeTextActive]}>{employee.name}</Text></Pressable>)}</View>
        {!form.watch("employee_id") ? <Controller control={form.control} name="recipient_name" render={({ field, fieldState }) => <FormField label="Or enter labourer name" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} /> : null}
      </> : null}

      {isGroupRole ? <View style={styles.field}><Text style={styles.label}>RESPONSIBLE MANAGER</Text>{managers.isPending ? <LoadingState label="Loading managers" /> : managers.data?.map((manager) => <Pressable key={manager.id} style={[styles.typeButton, form.watch("responsible_manager_id") === manager.id && styles.typeActive]} onPress={() => form.setValue("responsible_manager_id", manager.id, { shouldValidate: true })}><Text style={styles.typeText}>{manager.name} · {manager.role.replaceAll("_", " ")}</Text></Pressable>)}{!managers.data?.length && !managers.isPending ? <Text style={styles.error}>Add a Manager or Asst Manager before recording an expense.</Text> : null}</View> : null}

      <Controller control={form.control} name="amount" render={({ field, fieldState }) => <FormField label="Amount (INR)" keyboardType="decimal-pad" value={type === "diesel" ? calculatedAmount ?? "" : field.value} editable={type !== "diesel"} onChangeText={field.onChange} error={fieldState.error?.message} />} />
      <Controller control={form.control} name="description" render={({ field }) => <FormField label="Description" value={field.value} onChangeText={field.onChange} multiline />} />
      <ActionButton title={bill ? `Bill attached: ${bill.fileName ?? "photo"}` : "Attach bill photo"} icon={Camera} variant="secondary" onPress={() => void chooseBill()} />
      {feedback ? <Text accessibilityRole="alert" style={styles.error}>{feedback}</Text> : null}
      <ActionButton title="Save expense" loading={mutation.isPending} onPress={submit} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  label: { ...typography.caption, fontWeight: "700" },
  types: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  typeButton: { borderWidth: 1, borderColor: colors.line, borderRadius: 8, backgroundColor: colors.surface, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  typeActive: { borderColor: colors.forest, backgroundColor: "#E8F1EB" },
  typeText: { fontSize: 13, color: colors.ink, textTransform: "capitalize" },
  typeTextActive: { color: colors.forestDark, fontWeight: "700" },
  twoFields: { flexDirection: "row", gap: spacing.md },
  flex: { flex: 1 },
  field: { gap: spacing.sm },
  error: { color: colors.error, fontSize: 13 },
});