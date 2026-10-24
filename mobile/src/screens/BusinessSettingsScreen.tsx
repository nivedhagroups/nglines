import React, { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Save } from "lucide-react-native";
import { ActionButton } from "../components/ActionButton";
import { FormField } from "../components/FormField";
import { EmptyState, ErrorState, LoadingState } from "../components/QueryState";
import { PageTitle } from "../components/PageTitle";
import { Screen } from "../components/Screen";
import { resources } from "../services/resources";
import { useAuth } from "../state/AuthContext";
import { ApiError } from "../services/api";
import { colors, spacing, typography } from "../theme";

const gstinPattern = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
const businessSchema = z.object({ legal_name: z.string().trim().min(1), display_name: z.string().trim().min(1), gstin: z.union([z.string().regex(gstinPattern), z.literal("")]), gst_state_code: z.union([z.string().regex(/^\d{2}$/), z.literal("")]), address: z.string(), invoice_footer: z.string() });
type BusinessValues = z.infer<typeof businessSchema>;

export function BusinessSettingsScreen() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const role = auth.activeBusiness?.role;
  const canEditBusiness = role === "admin" || role === "super_admin";
  const canEditGst = canEditBusiness || role === "ceo";
  const query = useQuery({ queryKey: ["business-settings", auth.activeBusiness?.id], queryFn: resources.businessSettings, enabled: Boolean(auth.activeBusiness) });
  const brickTypes = useQuery({ queryKey: ["brick-types", auth.activeBusiness?.id], queryFn: resources.brickTypes, enabled: Boolean(auth.activeBusiness && canEditBusiness) });
  const form = useForm<BusinessValues>({ resolver: zodResolver(businessSchema), defaultValues: { legal_name: "", display_name: "", gstin: "", gst_state_code: "", address: "", invoice_footer: "" } });
  const [gstRate, setGstRate] = useState("");
  const [gstDate, setGstDate] = useState(new Date().toISOString().slice(0, 10));
  const [brickName, setBrickName] = useState("");
  const [brickTypeId, setBrickTypeId] = useState("");
  const [brickRate, setBrickRate] = useState("");
  const [brickDate, setBrickDate] = useState(new Date().toISOString().slice(0, 10));
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (!query.data) return;
    form.reset({ legal_name: String(query.data.legal_name ?? ""), display_name: String(query.data.display_name ?? ""), gstin: String(query.data.gstin ?? ""), gst_state_code: String(query.data.gst_state_code ?? ""), address: String(query.data.address ?? ""), invoice_footer: String(query.data.invoice_footer ?? "") });
  }, [form, query.data]);

  const refresh = async () => queryClient.invalidateQueries({ queryKey: ["business-settings", auth.activeBusiness?.id] });
  const saveBusiness = useMutation({ mutationFn: (values: BusinessValues) => resources.updateBusinessSettings({ ...values, gstin: values.gstin || null, gst_state_code: values.gst_state_code || null }), onSuccess: refresh, onError: (error) => setFeedback(error instanceof ApiError ? error.message : "Could not save business details") });
  const saveGst = useMutation({ mutationFn: () => resources.createGstRate(gstRate, gstDate), onSuccess: async () => { setGstRate(""); await refresh(); }, onError: (error) => setFeedback(error instanceof Error ? error.message : "Could not save GST rate") });
  const addBrickType = useMutation({ mutationFn: () => resources.createBrickType(brickName.trim()), onSuccess: async () => { setBrickName(""); await queryClient.invalidateQueries({ queryKey: ["brick-types", auth.activeBusiness?.id] }); }, onError: (error) => setFeedback(error instanceof Error ? error.message : "Could not add brick type") });
  const addBrickRate = useMutation({ mutationFn: () => resources.createBrickRate(brickTypeId, brickRate, brickDate), onSuccess: () => { setBrickRate(""); setFeedback("Brick rate saved"); }, onError: (error) => setFeedback(error instanceof Error ? error.message : "Could not save brick rate") });

  return (
    <Screen>
      <PageTitle eyebrow={auth.activeBusiness?.name.toUpperCase()} title="Business settings" />
      {query.isPending ? <LoadingState /> : query.isError ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()} /> : <>
        <View style={styles.section}><Text style={styles.heading}>Company details</Text>
          {(["legal_name", "display_name", "gstin", "gst_state_code", "address", "invoice_footer"] as const).map((name) => <Controller key={name} control={form.control} name={name} render={({ field, fieldState }) => <FormField label={name.replaceAll("_", " ")} value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} autoCapitalize={name === "gstin" ? "characters" : "sentences"} multiline={name === "address" || name === "invoice_footer"} editable={canEditBusiness} />} />)}
          {canEditBusiness ? <ActionButton title="Save company details" icon={Save} loading={saveBusiness.isPending} onPress={form.handleSubmit((values) => saveBusiness.mutate(values))} /> : null}
        </View>
        {canEditGst ? <View style={styles.section}><Text style={styles.heading}>GST rate</Text><Text style={styles.current}>Current rate: {String(query.data.current_gst_rate ?? "Not configured")}%</Text><View style={styles.pair}><View style={styles.flex}><FormField label="Rate %" keyboardType="decimal-pad" value={gstRate} onChangeText={setGstRate} /></View><View style={styles.flex}><FormField label="Effective from" placeholder="YYYY-MM-DD" value={gstDate} onChangeText={setGstDate} /></View></View><ActionButton title="Add effective rate" loading={saveGst.isPending} disabled={!gstRate} onPress={() => saveGst.mutate()} /></View> : null}
        {canEditBusiness ? <View style={styles.section}><Text style={styles.heading}>Brick types and rates</Text>
          <View style={styles.pair}><View style={styles.flex}><FormField label="New brick type" value={brickName} onChangeText={setBrickName} /></View><ActionButton title="Add" variant="secondary" onPress={() => brickName.trim() && addBrickType.mutate()} /></View>
          {brickTypes.isPending ? <LoadingState label="Loading brick types" /> : !brickTypes.data?.data.length ? <EmptyState title="No brick types" detail="Add a brick type before setting its rate." /> : <View style={styles.choices}>{brickTypes.data.data.map((brick) => <Pressable key={brick.id} style={[styles.choice, brickTypeId === brick.id && styles.choiceSelected]} onPress={() => setBrickTypeId(brick.id)}><Text style={styles.choiceText}>{brick.name}</Text></Pressable>)}</View>}
          <View style={styles.pair}><View style={styles.flex}><FormField label="Rate per brick (INR)" keyboardType="decimal-pad" value={brickRate} onChangeText={setBrickRate} /></View><View style={styles.flex}><FormField label="Effective from" placeholder="YYYY-MM-DD" value={brickDate} onChangeText={setBrickDate} /></View></View>
          <ActionButton title="Save brick rate" loading={addBrickRate.isPending} disabled={!brickTypeId || !brickRate} variant="secondary" onPress={() => addBrickRate.mutate()} />
        </View> : null}
      </>}
      {feedback ? <Text accessibilityRole="alert" style={styles.feedback}>{feedback}</Text> : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { padding: spacing.md, gap: spacing.md, borderWidth: 1, borderColor: colors.line, borderRadius: 8, backgroundColor: colors.surface },
  heading: { ...typography.heading },
  current: { ...typography.body, color: colors.forestDark, fontWeight: "700" },
  pair: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm },
  flex: { flex: 1 },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  choice: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderWidth: 1, borderColor: colors.line, borderRadius: 8 },
  choiceSelected: { borderColor: colors.forest, backgroundColor: "#E8F1EB" },
  choiceText: { color: colors.ink },
  feedback: { color: colors.error },
});