import React from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { NavigationContainer, useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { BookOpenText, ChartNoAxesCombined, CircleDollarSign, ContactRound, Ellipsis } from "lucide-react-native";
import type { MainTabParamList, RootStackParamList } from "./types";
import { useAuth } from "../state/AuthContext";
import { LoginScreen } from "../screens/LoginScreen";
import { ChangePasswordScreen } from "../screens/ChangePasswordScreen";
import { DashboardScreen } from "../screens/DashboardScreen";
import { InvoiceListScreen } from "../screens/InvoiceListScreen";
import { ExpenseListScreen } from "../screens/ExpenseListScreen";
import { CustomerListScreen } from "../screens/CustomerListScreen";
import { MoreScreen } from "../screens/MoreScreen";
import { ProfileScreen } from "../screens/ProfileScreen";
import { ResourceListScreen } from "../screens/ResourceListScreen";
import { InvoiceDetailScreen } from "../screens/InvoiceDetailScreen";
import { ExpenseDetailScreen } from "../screens/ExpenseDetailScreen";
import { CustomerDetailScreen } from "../screens/CustomerDetailScreen";
import { CreateEstimateScreen, CreateInvoiceScreen, EditInvoiceScreen } from "../screens/CreateInvoiceScreen";
import { CreateExpenseScreen } from "../screens/CreateExpenseScreen";
import { UserManagementScreen } from "../screens/UserManagementScreen";
import { BusinessSettingsScreen } from "../screens/BusinessSettingsScreen";
import { colors, spacing, typography } from "../theme";

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tabs = createBottomTabNavigator<MainTabParamList>();

function MainTabs() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  return (
    <Tabs.Navigator
      screenOptions={({ route }) => ({
        headerTitle: "Nivedha Groups",
        headerTitleStyle: { fontSize: 16, fontWeight: "700", color: colors.ink },
        headerStyle: { backgroundColor: colors.paper },
        headerShadowVisible: false,
        tabBarActiveTintColor: colors.forest,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: { height: 62, paddingTop: 7, paddingBottom: 7, borderTopColor: colors.line, backgroundColor: colors.surface },
        tabBarLabelStyle: { fontSize: 10, fontWeight: "700" },
        tabBarIcon: ({ color, size }) => {
          const Icon = route.name === "Overview" ? ChartNoAxesCombined : route.name === "Invoices" ? BookOpenText : route.name === "Expenses" ? CircleDollarSign : route.name === "Customers" ? ContactRound : Ellipsis;
          return <Icon size={size} color={color} />;
        },
      })}
    >
      <Tabs.Screen name="Overview" component={DashboardScreen} options={{ title: "Overview" }} />
      <Tabs.Screen name="Invoices" component={InvoiceListScreen} options={{ title: "Invoices" }} />
      <Tabs.Screen name="Expenses" component={ExpenseListScreen} options={{ title: "Expenses" }} />
      <Tabs.Screen name="Customers" component={CustomerListScreen} options={{ title: "Customers" }} />
      <Tabs.Screen name="More" component={MoreScreen} options={{ title: "More" }} />
    </Tabs.Navigator>
  );
}

function AuthenticatedStack() {
  return (
    <Stack.Navigator screenOptions={{ headerTintColor: colors.forest, headerStyle: { backgroundColor: colors.paper }, headerShadowVisible: false, contentStyle: { backgroundColor: colors.paper } }}>
      <Stack.Screen name="Main" component={MainTabs} options={{ headerShown: false }} />
      <Stack.Screen name="CreateInvoice" component={CreateInvoiceScreen} options={{ title: "New invoice", presentation: "modal" }} />
      <Stack.Screen name="EditInvoice" component={EditInvoiceScreen} options={{ title: "Correct invoice", presentation: "modal" }} />
      <Stack.Screen name="CreateEstimate" component={CreateEstimateScreen} options={{ title: "New estimate", presentation: "modal" }} />
      <Stack.Screen name="CreateExpense" component={CreateExpenseScreen} options={{ title: "Record expense", presentation: "modal" }} />
      <Stack.Screen name="InvoiceDetail" component={InvoiceDetailScreen} options={{ title: "Invoice" }} />
      <Stack.Screen name="ExpenseDetail" component={ExpenseDetailScreen} options={{ title: "Expense" }} />
      <Stack.Screen name="CustomerDetail" component={CustomerDetailScreen} options={{ title: "Customer" }} />
      <Stack.Screen name="ResourceList" component={ResourceListScreen} options={{ title: "Records" }} />
      <Stack.Screen name="Profile" component={ProfileScreen} options={{ title: "Profile" }} />
      <Stack.Screen name="UserManagement" component={UserManagementScreen} options={{ title: "User management" }} />
      <Stack.Screen name="BusinessSettings" component={BusinessSettingsScreen} options={{ title: "Business settings" }} />
    </Stack.Navigator>
  );
}

export function RootNavigator() {
  const auth = useAuth();
  if (!auth.ready) {
    return <View style={styles.loading}><ActivityIndicator size="large" color={colors.forest} /><Text style={styles.loadingText}>Restoring secure session</Text></View>;
  }
  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.paper } }}>
        {auth.user?.must_change_password
          ? <Stack.Screen name="ChangePassword" component={ChangePasswordScreen} />
          : auth.user
            ? <Stack.Screen name="Authenticated" component={AuthenticatedStack} />
            : <Stack.Screen name="Login" component={LoginScreen} />}
      </Stack.Navigator>
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.md, backgroundColor: colors.paper },
  loadingText: { ...typography.caption },
});