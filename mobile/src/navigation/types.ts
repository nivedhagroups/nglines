export type RootStackParamList = {
  Login: undefined;
  Main: undefined;
  CreateInvoice: undefined;
  EditInvoice: { invoiceId: string };
  CreateEstimate: undefined;
  CreateExpense: undefined;
  InvoiceDetail: { invoiceId: string };
  CustomerDetail: { customerId: string };
  ExpenseDetail: { expenseId: string };
  ResourceList: { resource: "settings" | "users" | "audit" | "notifications" | "estimates" | "flags" };
  UserManagement: undefined;
  BusinessSettings: undefined;
  Profile: undefined;
};

export type MainTabParamList = {
  Overview: undefined;
  Invoices: undefined;
  Expenses: undefined;
  Customers: undefined;
  More: undefined;
};