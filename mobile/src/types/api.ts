export type OrganizationRole = "super_admin" | "admin" | "ceo";
export type BusinessRole = "manager" | "asst_manager";
export type AppRole = OrganizationRole | BusinessRole;

export type BusinessAccess = {
  id: string;
  name: string;
  role: AppRole;
};

export type SessionUser = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  organization_role: OrganizationRole | null;
  must_change_password: boolean;
};

export type SessionPayload = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: "Bearer";
  user: SessionUser;
  businesses: BusinessAccess[];
};

export type ApiErrorShape = {
  error: { code: string; message: string; fields?: { field: string; message: string }[] };
  request_id?: string;
};

export type Page<T> = {
  data: T[];
  page: { limit: number; next_cursor: string | null };
  request_id?: string;
};

export type DashboardPeriod = { from: string; to: string; amount: string };
export type DashboardSummary = {
  timezone: string;
  currency: string;
  sales: Record<string, DashboardPeriod>;
  expenses: Record<string, DashboardPeriod>;
};

export type Customer = {
  id: string;
  name: string;
  mobile: string;
  email: string | null;
  gstin: string | null;
  location: string | null;
};

export type InvoiceSummary = {
  id: string;
  invoice_number: string;
  invoice_date: string;
  customer_name: string;
  total_amount: string;
  status: string;
};

export type ExpenseSummary = {
  id: string;
  expense_type: string;
  expense_date: string;
  amount: string;
  description: string | null;
};