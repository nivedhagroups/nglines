import { apiRequest } from "./api";
import type {
  Customer,
  DashboardSummary,
  ExpenseSummary,
  InvoiceSummary,
  Page,
} from "../types/api";

type InvoiceCreate = {
  customer_id?: string;
  new_customer?: { name: string; mobile: string; email?: string; gstin?: string; location?: string };
  customer_gstin?: string;
  responsible_manager_id?: string;
  invoice_date: string;
  apply_gst: boolean;
  discount_percent: string;
  items: { brick_type_id: string; quantity: string }[];
};

type ExpenseCreate = {
  expense_type: string;
  category_id: string;
  expense_date: string;
  amount: string;
  description?: string;
  vehicle_id?: string;
  litres?: string;
  unit_rate?: string;
  employee_id?: string;
  salary_period?: string;
  recipient_name?: string;
  responsible_manager_id?: string;
};

export const resources = {
  dashboard: () => apiRequest<DashboardSummary>("/dashboard/summary"),
  invoices: (cursor?: string) =>
    apiRequest<Page<InvoiceSummary>>(`/invoices?limit=25${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`),
  invoice: (id: string) => apiRequest<Record<string, unknown>>(`/invoices/${id}`),
  updateInvoice: (id: string, body: InvoiceCreate) => apiRequest<Record<string, unknown>>(`/invoices/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  customer: (id: string, from?: string, to?: string) =>
    apiRequest<Record<string, unknown>>(`/customers/${id}${from || to ? `?${from ? `from=${encodeURIComponent(from)}` : ""}${from && to ? "&" : ""}${to ? `to=${encodeURIComponent(to)}` : ""}` : ""}`),
  createInvoice: (body: InvoiceCreate, idempotencyKey: string) =>
    apiRequest<Record<string, unknown>>("/invoices", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    }),
  createEstimate: (body: InvoiceCreate, idempotencyKey: string) =>
    apiRequest<Record<string, unknown>>("/estimates", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    }),
  expenses: (cursor?: string) =>
    apiRequest<Page<ExpenseSummary>>(`/expenses?limit=25${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`),
  expense: (id: string) => apiRequest<Record<string, unknown>>(`/expenses/${id}`),
  updateExpense: (id: string, body: Record<string, unknown>) => apiRequest<Record<string, unknown>>(`/expenses/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  createExpense: (body: ExpenseCreate) =>
    apiRequest<Record<string, unknown>>("/expenses", { method: "POST", body: JSON.stringify(body) }),
  customers: (query = "", cursor?: string) =>
    apiRequest<Page<Customer>>(`/customers?limit=30&q=${encodeURIComponent(query)}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`),
  brickTypes: () => apiRequest<Page<{ id: string; name: string }>>("/settings/brick-types?limit=100"),
  expenseCategories: () => apiRequest<Page<{ id: string; name: string; expense_type: string }>>("/settings/expense-categories?limit=100"),
  vehicles: () => apiRequest<Page<{ id: string; registration_number: string }>>("/settings/vehicles?limit=100"),
  employees: () => apiRequest<Page<{ id: string; name: string }>>("/settings/employees?limit=100"),
  managers: () => apiRequest<{ id: string; name: string; role: string }[]>("/settings/responsible-managers"),
  businessSettings: () => apiRequest<Record<string, unknown>>("/settings/business"),
  updateBusinessSettings: (body: Record<string, unknown>) => apiRequest<Record<string, unknown>>("/settings/business", { method: "PATCH", body: JSON.stringify(body) }),
  createGstRate: (rate: string, effectiveFrom: string) => apiRequest<Record<string, unknown>>("/settings/gst-rates", { method: "POST", body: JSON.stringify({ rate, effective_from: effectiveFrom }) }),
  createBrickType: (name: string) => apiRequest<{ id: string }>("/settings/brick-types", { method: "POST", body: JSON.stringify({ name }) }),
  createBrickRate: (brickTypeId: string, rate: string, effectiveFrom: string) => apiRequest<Record<string, unknown>>("/settings/brick-rates", { method: "POST", body: JSON.stringify({ brick_type_id: brickTypeId, rate, effective_from: effectiveFrom }) }),
  auditLogs: () => apiRequest<Page<Record<string, unknown>>>("/audit-logs?limit=30"),
  users: () => apiRequest<Page<Record<string, unknown>>>("/users?limit=30"),
  estimates: () => apiRequest<Page<Record<string, unknown>>>("/estimates?limit=30"),
  convertEstimate: (id: string, invoiceDate: string, key: string) =>
    apiRequest<Record<string, unknown>>(`/estimates/${id}/convert`, {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ invoice_date: invoiceDate }),
    }),
  notifications: () => apiRequest<Page<Record<string, unknown>>>("/notifications?limit=30"),
  flags: () => apiRequest<Page<Record<string, unknown>>>("/flags?limit=30"),
  flagResponse: (id: string, responseText: string) => apiRequest(`/flags/${id}/response`, { method: "POST", body: JSON.stringify({ response_text: responseText }) }),
  flagCorrected: (id: string, summary: string) => apiRequest(`/flags/${id}/corrected`, { method: "POST", body: JSON.stringify({ response_text: summary }) }),
  resolveFlag: (id: string, note: string) => apiRequest(`/flags/${id}/resolve`, { method: "POST", body: JSON.stringify({ resolution_note: note || undefined }) }),
  reflag: (id: string, reason: string) => apiRequest(`/flags/${id}/reflag`, { method: "POST", body: JSON.stringify({ response_text: reason }) }),
};