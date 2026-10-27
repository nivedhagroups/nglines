import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { KeyRound, Plus, UserRound, UserX } from "lucide-react-native";
import { ActionButton } from "../components/ActionButton";
import { FormField } from "../components/FormField";
import { EmptyState, ErrorState, LoadingState } from "../components/QueryState";
import { PageTitle } from "../components/PageTitle";
import { Screen } from "../components/Screen";
import { apiRequest } from "../services/api";
import { resources } from "../services/resources";
import { useAuth } from "../state/AuthContext";
import { colors, spacing, typography } from "../theme";

const roles = ["manager", "asst_manager", "ceo", "admin", "super_admin"] as const;
const schema = z.object({ name: z.string().trim().min(1), email: z.union([z.string().email(), z.literal("")]), phone: z.union([z.string().regex(/^(?:\+91)?[6-9][0-9]{9}$/), z.literal("")]), role: z.enum(roles) }).refine((value) => Boolean(value.email || value.phone), { path: ["phone"], message: "Email or phone is required" });
type Values = z.infer<typeof schema>;
type TemporaryPasswordResult = { temporary_password: string | null; invite_sent: boolean | null };

export function UserManagementScreen() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const isSuperAdmin = auth.user?.organization_role === "super_admin";
  const users = useQuery({ queryKey: ["users", auth.activeBusiness?.id], queryFn: resources.users, enabled: Boolean(auth.activeBusiness) });
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { name: "", email: "", phone: "", role: "manager" } });

  const create = useMutation({
    mutationFn: async (values: Values) => {
      const groupRole = values.role === "admin" || values.role === "ceo" || values.role === "super_admin";
      return apiRequest<TemporaryPasswordResult>("/users", { method: "POST", body: JSON.stringify({
        name: values.name,
        email: values.email || undefined,
        phone: values.phone || undefined,
        organization_role: groupRole ? values.role : undefined,
        business_id: groupRole ? undefined : auth.activeBusiness?.id,
        business_role: groupRole ? undefined : values.role,
      }) });
    },
    onSuccess: async (result) => {
      form.reset();
      setShowForm(false);
      setFeedback(result.temporary_password
        ? `Temporary password (share once): ${result.temporary_password}`
        : result.invite_sent
          ? "Account created. Temporary password sent by email; the user must change it at first sign-in."
          : "Account created.");
      await queryClient.invalidateQueries({ queryKey: ["users", auth.activeBusiness?.id] });
    },
    onError: (error) => setFeedback(error instanceof Error ? error.message : "Could not create user"),
  });
  const resetPassword = useMutation({
    mutationFn: (id: string) => apiRequest<TemporaryPasswordResult>(`/users/${id}/temporary-password`, { method: "POST" }),
    onSuccess: (result) => setFeedback(result.temporary_password
      ? `Temporary password (share once): ${result.temporary_password}`
      : "Temporary password sent by email."),
    onError: (error) => setFeedback(error instanceof Error ? error.message : "Could not reset password"),
  });
  const deactivate = useMutation({
    mutationFn: (id: string) => apiRequest<void>(`/users/${id}`, { method: "DELETE" }),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ["users", auth.activeBusiness?.id] }),
    onError: (error) => setFeedback(error instanceof Error ? error.message : "Could not deactivate user"),
  });

  const submit = form.handleSubmit((values) => {
    setFeedback(null);
    if (values.role === "super_admin" && !isSuperAdmin) {
      setFeedback("Only a Super Admin can grant the Super Admin role.");
      return;
    }
    create.mutate(values);
  });

  return (
    <Screen>
      <PageTitle eyebrow={auth.activeBusiness?.name.toUpperCase()} title="User management" trailing={<Pressable accessibilityRole="button" accessibilityLabel="Create user" style={styles.add} onPress={() => setShowForm((value) => !value)}><Plus size={20} color={colors.surface} /></Pressable>} />
      {feedback ? <Text accessibilityRole="alert" style={styles.feedback}>{feedback}</Text> : null}
      {showForm ? <View style={styles.form}>
        <Controller control={form.control} name="name" render={({ field, fieldState }) => <FormField label="Name" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} />
        <Controller control={form.control} name="email" render={({ field, fieldState }) => <FormField label="Email" autoCapitalize="none" keyboardType="email-address" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} />
        <Controller control={form.control} name="phone" render={({ field, fieldState }) => <FormField label="Phone" keyboardType="phone-pad" value={field.value} onChangeText={field.onChange} error={fieldState.error?.message} />} />
        <Text style={styles.label}>ROLE</Text>
        <View style={styles.roles}>{roles.filter((role) => role !== "super_admin" || isSuperAdmin).map((role) => <Pressable key={role} style={[styles.roleChoice, form.watch("role") === role && styles.selected]} onPress={() => form.setValue("role", role)}><Text style={styles.roleText}>{role.replaceAll("_", " ")}</Text></Pressable>)}</View>
        <Text style={styles.scope}>{["manager", "asst_manager"].includes(form.watch("role")) ? `Assigned to ${auth.activeBusiness?.name ?? "the selected business"}` : "Group-wide business access"}</Text>
        <ActionButton title="Create account" loading={create.isPending} onPress={submit} />
      </View> : null}
      {users.isPending ? <LoadingState label="Loading users" /> : users.isError ? <ErrorState message={users.error.message} onRetry={() => void users.refetch()} /> : !users.data?.data.length ? <EmptyState title="No users found" detail="Create a team account to grant business access." /> : users.data.data.map((user) => {
        const record = user as Record<string, unknown>;
        const id = String(record.id);
        return <View key={id} style={styles.row}>
          <View style={styles.personIcon}><UserRound size={18} color={colors.forest} /></View>
          <View style={styles.userInfo}><Text style={styles.name}>{String(record.name)}</Text><Text style={styles.meta}>{String(record.email ?? record.phone ?? "No login contact")}</Text><Text style={styles.meta}>{String(record.organization_role ?? "Business member").replaceAll("_", " ")}</Text></View>
          {id !== auth.user?.id ? <>
            <Pressable accessibilityRole="button" accessibilityLabel="Reset temporary password" onPress={() => resetPassword.mutate(id)} style={styles.deactivate}><KeyRound size={17} color={colors.forest} /></Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel="Deactivate user" onPress={() => deactivate.mutate(id)} style={styles.deactivate}><UserX size={17} color={colors.coral} /></Pressable>
          </> : null}
        </View>;
      })}
    </Screen>
  );
}

const styles = StyleSheet.create({
  add: { width: 44, height: 44, borderRadius: 8, backgroundColor: colors.forest, alignItems: "center", justifyContent: "center" },
  form: { padding: spacing.md, borderWidth: 1, borderColor: colors.line, borderRadius: 8, backgroundColor: colors.surface, gap: spacing.md },
  label: { ...typography.caption, fontWeight: "700" },
  roles: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  roleChoice: { borderWidth: 1, borderColor: colors.line, borderRadius: 8, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  selected: { borderColor: colors.forest, backgroundColor: "#E8F1EB" },
  roleText: { color: colors.ink, textTransform: "capitalize", fontSize: 13 },
  scope: { ...typography.caption },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.md, gap: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.line },
  personIcon: { width: 40, height: 40, borderRadius: 8, backgroundColor: "#E8F1EB", alignItems: "center", justifyContent: "center" },
  userInfo: { flex: 1, gap: 3 },
  name: { ...typography.body, fontWeight: "700" },
  meta: { ...typography.caption, textTransform: "capitalize" },
  deactivate: { width: 40, height: 40, borderRadius: 8, backgroundColor: "#FBECE8", alignItems: "center", justifyContent: "center" },
  feedback: { color: colors.forestDark, backgroundColor: "#EDF5E9", padding: spacing.md, borderRadius: 8 },
});