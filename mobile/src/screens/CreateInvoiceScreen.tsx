import React, { useEffect, useState } from "react";
import { Pressable, StyleSheet, Switch, Text, View } from "react-native";
import { Controller, useFieldArray, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { Plus, Trash2 } from "lucide-react-native";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { ActionButton } from "../components/ActionButton";
import { FormField } from "../components/FormField";
import { LoadingState } from "../components/QueryState";
import { PageTitle } from "../components/PageTitle";
import { Screen } from "../components/Screen";
import { ApiError } from "../services/api";
import { resources } from "../services/resources";
import { useAuth } from "../state/AuthContext";
import type { RootStackParamList } from "../navigation/types";
import { colors, spacing, typography } from "../theme";

const mobilePattern = /^(?:\+91)?[6-9][0-9]{9}$/;
const gstinPattern = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
const schema = z.object({
  invoice_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  customer_id: z.string().optional(),
  new_name: z.string().optional(),
  new_mobile: z.string().optional(),
  new_email: z.string().email().optional().or(z.literal("")),
  customer_gstin: z.string().regex(gstinPattern).optional().or(z.literal("")),
  brick_manager_id: z.string().optional(),
  apply_gst: z.boolean(),
  discount_percent: z.string().regex(/^\d{1,3}(\.\d{1,2})?$/),
  items: z.array(z.object({ brick_type_id: z.string().min(1, "Select a brick type"), quantity: z.string().regex(/^\d+(\.\d{1,3})?$/) })).min(1),
}).superRefine((value, context) => {
  const hasExisting = Boolean(value.customer_id);
  const hasNew = Boolean(value.new_name || value.new_mobile);
  if (hasExisting === hasNew) context.addIssue({ code: "custom", path: ["customer_id"], message: "Select a customer or enter a new customer" });
  if (hasNew && !value.new_name?.trim()) context.addIssue({ code: "custom", path: ["new_name"], message: "Customer name is required" });
  if (hasNew && !mobilePattern.test(value.new_mobile ?? "")) context.addIssue({ code: "custom", path: ["new_mobile"], message: "Enter a valid Indian mobile number" });
  if (Number(value.discount_percent) > 100) context.addIssue({ code: "custom", path: ["discount_percent"], message: "Discount cannot exceed 100%" });
});

type FormValues = z.infer<typeof schema>;

export function CreateInvoiceScreen({ mode = "invoice", invoiceId }: { mode?: "invoice" | "estimate"; invoiceId?: string }) {
  const auth = useAuth();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const queryClient = useQueryClient();
  const [newCustomer, setNewCustomer] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const customers = useQuery({ queryKey: ["customers", auth.activeBusiness?.id, "invoice-picker"], queryFn: () => resources.customers(), enabled: Boolean(auth.activeBusiness) });
  const brickTypes = useQuery({ queryKey: ["brick-types", auth.activeBusiness?.id], queryFn: resources.brickTypes, enabled: Boolean(auth.activeBusiness) });
  const managers = useQuery({ queryKey: ["responsible-managers", auth.activeBusiness?.id], queryFn: resources.managers, enabled: Boolean(auth.activeBusiness && auth.user?.organization_role) });
  const existingInvoice = useQuery({ queryKey: ["invoice", invoiceId], queryFn: () => resources.invoice(invoiceId!), enabled: Boolean(invoiceId) });
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { invoice_date: new Date().toISOString().slice(0, 10), customer_id: "", new_name: "", new_mobile: "", new_email: "", customer_gstin: "", brick_manager_id: "", apply_gst: false, discount_percent: "0", items: [{ brick_type_id: "", quantity: "1" }] },
  });
  const fields = useFieldArray({ control: form.control, name: "items" });
  const selectedItems = useWatch({ control: form.control, name: "items" });
  const customerList = customers.data?.data ?? [];
  const brickList = brickTypes.data?.data ?? [];
  const isGroupRole = Boolean(auth.user?.organization_role);

  useEffect(() => {
    if (!invoiceId || !existingInvoice.data) return;
    const invoice = existingInvoice.data;
    const items = Array.isArray(invoice.items) ? invoice.items as Record<string, unknown>[] : [];
    form.reset({
      invoice_date: String(invoice.invoice_date),
      customer_id: String(invoice.customer_id),
      new_name: "",
      new_mobile: "",
      new_email: "",
      customer_gstin: String(invoice.customer_gstin ?? ""),
      brick_manager_id: String(invoice.responsible_manager_id ?? ""),
      apply_gst: Boolean(invoice.apply_gst),
      discount_percent: String(invoice.discount_percent ?? "0"),
      items: items.map((item) => ({ brick_type_id: String(item.brick_type_id), quantity: String(item.quantity) })),
    });
  }, [existingInvoice.data, form, invoiceId]);

  const mutation = useMutation({
    mutationFn: async (values: FormValues) => {
      const body = {
        invoice_date: values.invoice_date,
        apply_gst: values.apply_gst,
        discount_percent: values.discount_percent || "0",
        customer_gstin: values.customer_gstin || undefined,
        customer_id: newCustomer ? undefined : values.customer_id,
        new_customer: newCustomer ? { name: values.new_name?.trim(), mobile: values.new_mobile, email: values.new_email || undefined, gstin: values.customer_gstin || undefined } : undefined,
        responsible_manager_id: isGroupRole ? values.brick_manager_id : undefined,
        items: values.items.map((item) => ({ brick_type_id: item.brick_type_id, quantity: item.quantity })),
      };
      const key = `invoice-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      if (invoiceId) return resources.updateInvoice(invoiceId, body);
      return mode === "invoice" ? resources.createInvoice(body, key) : resources.createEstimate(body, key);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["invoices", auth.activeBusiness?.id] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard", auth.activeBusiness?.id] });
      await queryClient.invalidateQueries({ queryKey: ["customers", auth.activeBusiness?.id] });
      await queryClient.invalidateQueries({ queryKey: ["estimates", auth.activeBusiness?.id] });
      if (invoiceId) await queryClient.invalidateQueries({ queryKey: ["invoice", invoiceId] });
      navigation.goBack();
    },
    onError: (error) => setFeedback(error instanceof ApiError ? error.message : "Unable to save invoice"),
  });

  const submit = form.handleSubmit((values) => {
    setFeedback(null);
    if (isGroupRole && !values.brick_manager_id) {
      setFeedback("Select the responsible Manager or Asst Manager.");
      return;
    }
    mutation.mutate(values);
  });

  return (
    <Screen>
      <PageTitle eyebrow={mode === "invoice" ? "SALES" : "ESTIMATION"} title={invoiceId ? "Correct invoice" : mode === "invoice" ? "New invoice" : "New estimate"} />
      {mode === "estimate" ? <Text style={styles.estimateLabel}>ESTIMATE – NOT A TAX INVOICE</Text> : null}
      <Controller control={form.control} name="invoice_date" render={({ field, fieldState }) => <FormField label="Invoice date" value={field.value} onChangeText={field.onChange} onBlur={field.onBlur} placeholder="YYYY-MM-DD" error={fieldState.error?.message} />} />
      <View style={styles.toggleRow}>
        <View style={styles.toggleText}><Text style={styles.section}>Customer</Text><Text style={styles.caption}>Choose a saved customer or add one inline.</Text></View>
        <Pressable accessibilityRole="button" onPress={() => { const next = !newCustomer; setNewCustomer(next); form.setValue("customer_id", ""); if (!next) { form.setValue("new_name", ""); form.setValue("new_mobile", ""); form.setValue("new_email", ""); } }}><Text style={styles.link}>{newCustomer ? "Choose existing" : "+ Add new"}</Text></Pressable>
      </View>
      {newCustomer ? <>
        <Controller control={form.control} name="new_name" render={({ field, fieldState }) => <FormField label="Customer name" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} />
        <Controller control={form.control} name="new_mobile" render={({ field, fieldState }) => <FormField label="Mobile" keyboardType="phone-pad" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} />
        <Controller control={form.control} name="new_email" render={({ field, fieldState }) => <FormField label="Email (optional)" keyboardType="email-address" autoCapitalize="none" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} />
      </> : customers.isPending ? <LoadingState label="Loading customers" /> : <View style={styles.choices}>{customerList.map((customer) => <Pressable key={customer.id} style={[styles.choice, form.watch("customer_id") === customer.id && styles.choiceSelected]} onPress={() => form.setValue("customer_id", customer.id, { shouldValidate: true })}><Text style={styles.choiceText}>{customer.name}  ·  {customer.mobile}</Text></Pressable>)}</View>}
      {form.formState.errors.customer_id ? <Text style={styles.error}>{form.formState.errors.customer_id.message}</Text> : null}
      <Controller control={form.control} name="customer_gstin" render={({ field, fieldState }) => <FormField label="Customer GSTIN (optional)" autoCapitalize="characters" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} />

      <View style={styles.rule} />
      <View style={styles.toggleRow}><Text style={styles.section}>Line items</Text><Pressable accessibilityRole="button" style={styles.iconButton} onPress={() => fields.append({ brick_type_id: "", quantity: "1" })}><Plus size={18} color={colors.forest} /></Pressable></View>
      {fields.fields.map((field, index) => (
        <View key={field.id} style={styles.lineItem}>
          <Text style={styles.caption}>ITEM {index + 1}</Text>
          <View style={styles.choices}>{brickList.map((brick) => <Pressable key={brick.id} style={[styles.choice, selectedItems?.[index]?.brick_type_id === brick.id && styles.choiceSelected]} onPress={() => form.setValue(`items.${index}.brick_type_id`, brick.id, { shouldValidate: true })}><Text style={styles.choiceText}>{brick.name}</Text></Pressable>)}</View>
          <View style={styles.quantityRow}>
            <View style={styles.quantity}><Controller control={form.control} name={`items.${index}.quantity`} render={({ field: input, fieldState }) => <FormField label="Quantity" keyboardType="decimal-pad" value={input.value} onChangeText={input.onChange} error={fieldState.error?.message} />} /></View>
            {fields.fields.length > 1 ? <Pressable accessibilityRole="button" accessibilityLabel={`Remove item ${index + 1}`} onPress={() => fields.remove(index)} style={styles.remove}><Trash2 size={18} color={colors.coral} /></Pressable> : null}
          </View>
        </View>
      ))}

      {isGroupRole ? <View style={styles.fieldWrap}><Text style={styles.caption}>RESPONSIBLE MANAGER</Text>{managers.isPending ? <LoadingState label="Loading managers" /> : managers.data?.map((manager) => <Pressable key={manager.id} style={[styles.choice, form.watch("brick_manager_id") === manager.id && styles.choiceSelected]} onPress={() => form.setValue("brick_manager_id", manager.id, { shouldValidate: true })}><Text style={styles.choiceText}>{manager.name}  ·  {manager.role.replaceAll("_", " ")}</Text></Pressable>)}{!managers.data?.length && !managers.isPending ? <Text style={styles.error}>Add a Manager or Asst Manager before creating an invoice.</Text> : null}</View> : null}

      <View style={styles.switchRow}><View><Text style={styles.section}>Apply GST</Text><Text style={styles.caption}>Uses the current business GST rate.</Text></View><Controller control={form.control} name="apply_gst" render={({ field }) => <Switch value={field.value} onValueChange={field.onChange} trackColor={{ false: colors.line, true: colors.forest }} />} /></View>
      <Controller control={form.control} name="discount_percent" render={({ field, fieldState }) => <FormField label="Discount %" keyboardType="decimal-pad" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} />
      {feedback ? <Text accessibilityRole="alert" style={styles.error}>{feedback}</Text> : null}
      <ActionButton title={invoiceId ? "Save invoice correction" : mode === "invoice" ? "Create invoice" : "Create estimate"} loading={mutation.isPending} disabled={Boolean(invoiceId && existingInvoice.isPending)} onPress={submit} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { ...typography.heading },
  caption: { ...typography.caption },
  link: { color: colors.forest, fontWeight: "700" },
  toggleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md },
  toggleText: { flex: 1, gap: 4 },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  choice: { borderWidth: 1, borderColor: colors.line, borderRadius: 8, backgroundColor: colors.surface, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  choiceSelected: { borderColor: colors.forest, backgroundColor: "#E8F1EB" },
  choiceText: { color: colors.ink, fontSize: 13 },
  rule: { height: 1, backgroundColor: colors.line },
  lineItem: { gap: spacing.sm, padding: spacing.md, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.line, borderRadius: 8 },
  quantityRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.md },
  quantity: { flex: 1 },
  remove: { width: 46, height: 46, borderWidth: 1, borderColor: colors.line, borderRadius: 8, alignItems: "center", justifyContent: "center", marginBottom: 20 },
  iconButton: { width: 40, height: 40, borderRadius: 8, backgroundColor: "#E8F1EB", alignItems: "center", justifyContent: "center" },
  fieldWrap: { gap: spacing.sm },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderTopWidth: 1, borderBottomWidth: 1, borderColor: colors.line, paddingVertical: spacing.md },
  error: { color: colors.error, fontSize: 13 },
  estimateLabel: { color: colors.coral, fontSize: 12, fontWeight: "800" },
});

export function CreateEstimateScreen() {
  return <CreateInvoiceScreen mode="estimate" />;
}

export function EditInvoiceScreen({ route }: { route: { params: { invoiceId: string } } }) {
  return <CreateInvoiceScreen invoiceId={route.params.invoiceId} />;
}