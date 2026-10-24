import React, { useState } from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { Bell, Building2, ChevronDown, ClipboardList, FileText, LogOut, Settings2, ShieldCheck, UserRound, Users } from "lucide-react-native";
import { PageTitle } from "../components/PageTitle";
import { Screen } from "../components/Screen";
import { useAuth } from "../state/AuthContext";
import type { RootStackParamList } from "../navigation/types";
import { colors, spacing, typography } from "../theme";

export function MoreScreen() {
  const auth = useAuth();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [businessPicker, setBusinessPicker] = useState(false);
  const role = auth.activeBusiness?.role;
  const isSuperAdmin = auth.user?.organization_role === "super_admin";
  const canManageUsers = role === "admin" || isSuperAdmin;
  const canManageSettings = role === "admin" || role === "super_admin" || role === "ceo";
  const openList = (resource: "settings" | "users" | "audit" | "notifications" | "estimates" | "flags") => navigation.navigate("ResourceList", { resource });

  return (
    <Screen>
      <PageTitle eyebrow="ACCOUNT" title="More" />
      <Pressable accessibilityRole="button" style={styles.business} onPress={() => setBusinessPicker(true)}>
        <View style={styles.businessIcon}><Building2 size={19} color={colors.forest} /></View>
        <View style={styles.businessText}><Text style={styles.small}>ACTIVE BUSINESS</Text><Text style={styles.businessName}>{auth.activeBusiness?.name ?? "Select a business"}</Text></View>
        <ChevronDown size={18} color={colors.muted} />
      </Pressable>
      <View style={styles.menu}>
        <MenuRow icon={FileText} label="Estimates" onPress={() => openList("estimates")} />
        <MenuRow icon={Bell} label="Notifications" onPress={() => openList("notifications")} />
        <MenuRow icon={ShieldCheck} label="Doubtful transactions" onPress={() => openList("flags")} />
        {canManageSettings ? <MenuRow icon={Settings2} label="Business settings" onPress={() => navigation.navigate("BusinessSettings")} /> : null}
        {canManageUsers ? <MenuRow icon={Users} label="User management" onPress={() => navigation.navigate("UserManagement")} /> : null}
        {isSuperAdmin ? <MenuRow icon={ShieldCheck} label="Audit log" onPress={() => openList("audit")} /> : null}
        <MenuRow icon={UserRound} label="Profile" onPress={() => navigation.navigate("Profile")} />
        <MenuRow icon={LogOut} label="Sign out" danger onPress={() => void auth.logout()} />
      </View>
      <Text style={styles.role}>Signed in as {role?.replaceAll("_", " ") ?? "team member"}</Text>
      <Modal visible={businessPicker} transparent animationType="fade" onRequestClose={() => setBusinessPicker(false)}>
        <Pressable style={styles.modalBackdrop} onPress={() => setBusinessPicker(false)}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Choose business</Text>
            {auth.businesses.map((business) => (
              <Pressable key={business.id} style={styles.businessOption} onPress={() => { void auth.selectBusiness(business.id); setBusinessPicker(false); }}>
                <Text style={styles.businessName}>{business.name}</Text><Text style={styles.small}>{business.role.replaceAll("_", " ")}</Text>
              </Pressable>
            ))}
          </View>
        </Pressable>
      </Modal>
    </Screen>
  );
}

function MenuRow({ icon: Icon, label, onPress, danger = false }: { icon: typeof UserRound; label: string; onPress: () => void; danger?: boolean }) {
  return (
    <Pressable accessibilityRole="button" style={styles.menuRow} onPress={onPress}>
      <Icon size={19} color={danger ? colors.coral : colors.forest} />
      <Text style={[styles.menuLabel, danger && styles.danger]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  business: { minHeight: 70, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.line, borderRadius: 8, padding: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.md },
  businessIcon: { width: 40, height: 40, borderRadius: 8, backgroundColor: "#E8F1EB", alignItems: "center", justifyContent: "center" },
  businessText: { flex: 1, gap: 3 },
  businessName: { ...typography.body, fontWeight: "700" },
  small: { ...typography.caption, textTransform: "uppercase", fontWeight: "700" },
  menu: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.line, borderRadius: 8, overflow: "hidden" },
  menuRow: { flexDirection: "row", minHeight: 54, alignItems: "center", paddingHorizontal: spacing.md, gap: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.line },
  menuLabel: { ...typography.body, flex: 1, fontWeight: "600" },
  danger: { color: colors.coral },
  role: { ...typography.caption },
  modalBackdrop: { flex: 1, justifyContent: "center", padding: spacing.lg, backgroundColor: "#17252299" },
  modal: { padding: spacing.lg, borderRadius: 8, backgroundColor: colors.surface, gap: spacing.md },
  modalTitle: { ...typography.heading },
  businessOption: { borderTopWidth: 1, borderTopColor: colors.line, paddingTop: spacing.md, gap: spacing.xs },
});