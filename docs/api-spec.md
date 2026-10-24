# Phase 1 API Specification

Base path: `/api/v1`. All endpoints use HTTPS and JSON except file upload/download and PDF responses. UUIDs are JSON strings. API timestamps are RFC 3339 with an explicit timezone; dates are ISO `YYYY-MM-DD`. The business timezone defaults to `Asia/Kolkata` and money is represented as decimal strings to avoid client floating-point errors.

## Request Context

- Authenticated endpoints require `Authorization: Bearer <access_token>`.
- Business-scoped endpoints require `X-Business-ID: <uuid>`. The API resolves access from the authenticated user's organization role or active `business_memberships`; it never trusts a `business_id` supplied in a request body.
- Super Admin, Admin, and CEO can select any active business. Manager and Asst Manager can select only a business with an active membership. A manager can only be assigned to one business at a time by user-management policy.
- Cross-business reads and writes return `404` rather than disclosing that another business's record exists.
- All list endpoints are paginated. Default `limit=25`, maximum `limit=100`; cursor pagination uses opaque `next_cursor` tokens. Filters are applied before pagination.
- Financial `DELETE` operations are soft deletes. Audit records are created in the same database transaction as each successful financial, configuration, user, or flag mutation.

## Standard Responses

Successful resource response:

```json
{
  "data": {
    "id": "f13c6b42-9ba8-49c0-b928-08dc3abfa5b0",
    "business_id": "0c0460be-321f-4050-94b6-51a9fc102299"
  },
  "request_id": "5ac8ef20-6282-4693-937c-5938bb22a87e"
}
```

Paginated response:

```json
{
  "data": [],
  "page": { "limit": 25, "next_cursor": null },
  "request_id": "5ac8ef20-6282-4693-937c-5938bb22a87e"
}
```

Error response:

```json
{
  "error": {
    "code": "validation_error",
    "message": "The request is invalid.",
    "fields": [{ "field": "mobile", "message": "Enter a valid mobile number." }]
  },
  "request_id": "5ac8ef20-6282-4693-937c-5938bb22a87e"
}
```

Common status codes: `400` malformed request or invalid state transition; `401` missing/expired authentication; `403` role not permitted; `404` missing or out-of-scope resource; `409` uniqueness, sequence, or state conflict; `422` field validation; `429` OTP/API rate limit; `500` unexpected server error. Error codes are stable machine-readable identifiers.

## Authentication and Profile

| Method and path | Request | Response / access |
| --- | --- | --- |
| `POST /auth/otp/request` | `{ "identifier": "person@example.com" }` or phone; optional `channel: "email" | "sms"` when identifier is ambiguous | `202 { "challenge_id", "expires_in_seconds": 300 }`; unauthenticated, rate limited. Never reveals whether an account exists. |
| `POST /auth/otp/verify` | `{ "challenge_id", "code" }` | `200 { "access_token", "expires_in", "refresh_token", "user", "businesses" }`; code is six digits, maximum attempts enforced. |
| `POST /auth/refresh` | `{ "refresh_token" }` | Rotated access/refresh token pair; old refresh token is invalidated. |
| `POST /auth/logout` | `{ "refresh_token" }` | `204`; revokes this refresh-token session. |
| `GET /auth/me` | None | Current user, organization role, memberships, accessible businesses. |
| `GET /profile` | None | Current user's name, email, phone, role, picture metadata. |
| `PATCH /profile` | `{ "name", "email", "phone" }` | Updates validated profile fields; role is read-only. |
| `POST /profile/picture` | `multipart/form-data`, image file | Validated image metadata and URL. |
| `GET /businesses` | `limit`, `cursor` | Accessible business list; global roles see all active businesses, managers see assigned business only. |
| `POST /businesses` | `{ "name", "slug", "legal_name", "gstin?", "gst_state_code?", "address?", "invoice_footer?" }` | Admin and Super Admin. Creates business settings and standard expense categories atomically. |

## Dashboard

| Method and path | Query | Response / access |
| --- | --- | --- |
| `GET /dashboard/summary` | Optional `from`, `to`; absent range returns current year, month, running week (Monday-Sunday), and today in `Asia/Kolkata` | `sales` and `expenses` each contain `annual`, `monthly`, `weekly`, `daily` totals; each period includes `from`, `to`, and `amount`. |
| `GET /dashboard/trends` | `from`, `to`, `interval=day|week|month` | Time-series buckets for sales and expenses. Manager, Asst Manager, CEO, Admin, Super Admin. |

All totals exclude soft-deleted and cancelled records. Estimates are not sales. The dashboard returns INR decimal strings; chart rendering is client-side.

## Customers

| Method and path | Request / query | Response / access |
| --- | --- | --- |
| `GET /customers` | `q`, `from`, `to`, `limit`, `cursor` | Paginated customers; `q` searches name/mobile/GSTIN. |
| `POST /customers` | `{ "name", "mobile", "email?", "gstin?", "location?" }` | `201` customer; name and normalized mobile required, mobile unique per business. |
| `GET /customers/{customer_id}` | `from`, `to`, `limit`, `cursor` | Customer detail, filtered invoice history, and purchase total for that date range. |
| `PATCH /customers/{customer_id}` | Any editable customer fields | Updated customer; audited. |
| `DELETE /customers/{customer_id}` | None | Soft delete; conflicts if an operation would violate a financial reference. |

Managers, Asst Managers, CEO, Admin, and Super Admin have access within the business scope.

## Invoices

| Method and path | Request / query | Response / access |
| --- | --- | --- |
| `GET /invoices` | `q`, `customer_id`, `status`, `from`, `to`, `limit`, `cursor` | Paginated invoices; search includes invoice number and customer name/mobile. |
| `POST /invoices` | Invoice payload below | `201` immutable issued invoice and calculated totals; Manager, Asst Manager, CEO, Admin, Super Admin. |
| `GET /invoices/{invoice_id}` | None | Header, line items, stored snapshots, totals, PDF metadata, share-link state. |
| `PATCH /invoices/{invoice_id}` | Editable fields only, with `If-Match` version/ETag | Updated invoice; audited. Updates must preserve numbering and regenerate PDF. Role policy permits invoice creators/authorized managers; Admin/Super Admin have full access. |
| `DELETE /invoices/{invoice_id}` | Required `reason` | Soft-cancel invoice; audited. Never hard deletes. |
| `POST /invoices/{invoice_id}/pdf` | None | Generates/regenerates PDF and returns file metadata. |
| `POST /invoices/{invoice_id}/share-links` | Optional `label` | Creates persistent, revocable link; raw token is returned only once. |
| `DELETE /invoices/{invoice_id}/share-links/{link_id}` | None | Revokes link. |
| `GET /shared/invoices/{token}` | Public opaque token | Downloads/streams invoice PDF if token is valid and not revoked. No account required. |

Invoice creation payload:

```json
{
  "customer_id": "f13c6b42-9ba8-49c0-b928-08dc3abfa5b0",
  "customer_gstin": "33ABCDE1234F1Z5",
  "responsible_manager_id": "1bb78b95-a7f2-42bb-91a4-1093129a5fc7",
  "invoice_date": "2026-10-24",
  "apply_gst": true,
  "discount_percent": "2.50",
  "items": [
    { "brick_type_id": "edab2049-0e46-4db2-bdd1-ff56bd2da414", "quantity": "1000" }
  ]
}
```

`customer_id` may be replaced with `new_customer: { name, mobile, email?, gstin?, location? }`; the customer and invoice are created atomically. Rates are resolved from the effective brick rate on the invoice date. By default, only Super Admin and Admin may override a unit rate; Manager and Asst Manager cannot. The server never trusts a client-submitted unit rate without this permission and records any override in the audit log. GST rate is selected from the effective business GST rate and snapshotted. Server calculates all amounts using decimal arithmetic and returns `subtotal`, `discount_amount`, `taxable_amount`, component taxes, and `total_amount`.

Invoice response includes `{ id, invoice_number, financial_year, invoice_date, customer, items, apply_gst, gst_rate, cgst_amount, sgst_amount, igst_amount, discount_percent, subtotal, discount_amount, taxable_amount, total_amount, status, pdf, created_at }`.

## Estimates

| Method and path | Request / query | Response / access |
| --- | --- | --- |
| `GET /estimates` | `q`, `customer_id`, `status`, `from`, `to`, `limit`, `cursor` | Paginated estimate list. |
| `POST /estimates` | Same structure as invoice creation | `201` estimate with `ESTIMATE – Not a Tax Invoice` watermark; same roles as invoice creation. |
| `GET /estimates/{estimate_id}` | None | Estimate and line-item snapshots. |
| `PATCH /estimates/{estimate_id}` | Editable estimate fields | Updated estimate, audited. |
| `DELETE /estimates/{estimate_id}` | Required `reason` | Soft delete; audited. |
| `POST /estimates/{estimate_id}/pdf` | None | Generate PDF. PDF and share artifact expire after 24 hours; record stays available. |
| `POST /estimates/{estimate_id}/share-links` | None | Link expires no later than 24 hours after creation. |
| `POST /estimates/{estimate_id}/convert` | `{ "invoice_date": "2026-10-24" }` | Creates a new invoice with fresh invoice number, copying estimate values and retaining a link to source estimate. Safe to retry with idempotency key. |
| `GET /shared/estimates/{token}` | Public opaque token | PDF download until expiration or revocation. |

## Expenses and Account Management

| Method and path | Request / query | Response / access |
| --- | --- | --- |
| `GET /expenses` | `type`, `category_id`, `vehicle_id`, `employee_id`, `from`, `to`, `limit`, `cursor` | Paginated expenses. |
| `POST /expenses` | Expense payload below | `201` expense; Manager, Asst Manager, CEO, Admin, Super Admin. |
| `GET /expenses/{expense_id}` | None | Expense and attachment metadata. |
| `PATCH /expenses/{expense_id}` | Editable expense fields, `If-Match` | Updated and audited; avoids overwriting concurrent changes. |
| `DELETE /expenses/{expense_id}` | Required `reason` | Soft delete and audit. |
| `POST /expenses/{expense_id}/attachments` | `multipart/form-data`, image/PDF | Adds bill attachment. |
| `GET /expenses/{expense_id}/attachments/{attachment_id}` | None | Authenticated business-scoped bill download. |
| `GET /reports/expenses/diesel` | `vehicle_id`, required `from`, `to`, `group_by=day|week|month` | Per-vehicle litres, rate, and amount totals. |
| `GET /employees/{employee_id}/advances` | `from`, `to`, `limit`, `cursor` | Advance, recovery entries, and outstanding balance. |
| `POST /expenses/{expense_id}/recoveries` | `{ "recovery_date", "amount", "notes?" }` | Records recovery against a salary-advance expense; amount cannot exceed remaining balance. |
| `GET /expense-categories` | `limit`, `cursor` | Active and inactive categories. |

Expense payload examples:

```json
{
  "expense_type": "diesel",
  "category_id": "28aff55b-286a-41e8-9d9f-a8af68c15f1e",
  "expense_date": "2026-10-24",
  "vehicle_id": "ca836a18-4155-471e-a7f4-91fe8b26676b",
  "litres": "40.00",
  "unit_rate": "92.50",
  "amount": "3700.00",
  "responsible_manager_id": "1bb78b95-a7f2-42bb-91a4-1093129a5fc7",
  "description": "Vehicle diesel"
}
```

```json
{
  "expense_type": "salary_advance",
  "category_id": "28aff55b-286a-41e8-9d9f-a8af68c15f1e",
  "expense_date": "2026-10-24",
  "employee_id": "1bb78b95-a7f2-42bb-91a4-1093129a5fc7",
  "recipient_name": "Labour name if not in employee master",
  "amount": "1500.00",
  "description": "Advance"
}
```

Diesel amount is computed as litres multiplied by unit rate; a submitted amount must match server rounding or be omitted. Salary period (`daily`, `weekly`, `monthly`) applies to salary expense entries, not advance recovery. Other types require their applicable fields only.

## Settings and Master Data

| Method and path | Request / query | Response / access |
| --- | --- | --- |
| `GET /settings/business` | None | Business details and current effective GST rate. |
| `POST /settings/business` | `{ "legal_name", "display_name", "gstin?", "gst_state_code?", "address?", "invoice_footer?" }` | Initializes settings once for a business. Admin, Super Admin. |
| `PATCH /settings/business` | Legal/display name, GSTIN/state, address, footer, timezone, logo metadata | Admin, Super Admin. Changes audited. |
| `GET /settings/gst-rates` | `from`, `to`, `limit`, `cursor` | Effective-date history. |
| `POST /settings/gst-rates` | `{ "rate", "effective_from" }` | Adds rate without rewriting issued documents. Super Admin, Admin, CEO. No overlapping effective ranges. |
| `GET /settings/brick-types` | `include_inactive?`, `limit`, `cursor` | Admin/master-data access; active types available for sales. |
| `POST /settings/brick-types` | `{ "name", "description?" }` | Create brick type; Admin, Super Admin. |
| `PATCH /settings/brick-types/{id}` | Name/description/active state | Update master data; audited. |
| `GET /settings/brick-rates` | `brick_type_id`, `from`, `to`, `limit`, `cursor` | Effective rate history. |
| `POST /settings/brick-rates` | `{ "brick_type_id", "rate", "effective_from" }` | Admin, Super Admin; prevents conflicting active periods. |
| `GET /settings/expense-categories` | `include_inactive?`, `limit`, `cursor` | Category list. |
| `POST /settings/expense-categories` | `{ "name", "expense_type" }` | Admin, Super Admin. |
| `PATCH /settings/expense-categories/{id}` | `{ "name?", "is_active?" }` | Admin, Super Admin. |
| `GET /settings/vehicles` | `include_inactive?`, `limit`, `cursor` | Vehicle list. |
| `POST /settings/vehicles` | `{ "registration_number", "description?" }` | Admin, Super Admin. |
| `PATCH /settings/vehicles/{id}` | Vehicle fields / active state | Admin, Super Admin. |
| `GET /settings/employees` | `q`, `include_inactive?`, `limit`, `cursor` | Employee list. |
| `GET /settings/responsible-managers` | None | Active Manager/Asst Manager options for assigning responsibility to transactions. Any authorized user in the selected business. |
| `POST /settings/employees` | `{ "name", "employee_code?", "mobile?" }` | Admin, Super Admin. |
| `PATCH /settings/employees/{id}` | Employee fields / active state | Admin, Super Admin. |
| `GET /users` | `business_id?`, `q`, `role?`, `status?`, `limit`, `cursor` | Admin and Super Admin only. |
| `POST /users` | `{ "name", "email?", "phone?", "organization_role?", "business_id?", "business_role?" }` | Admin and Super Admin. Manager/Asst Manager must have one business assignment; one of email/phone required. |
| `PATCH /users/{user_id}` | Editable profile, role/membership, active state | Admin and Super Admin; prevents self-escalation and invalid role/scope combinations. |
| `DELETE /users/{user_id}` | None | Deactivates user, revokes active sessions; no hard delete. Admin and Super Admin. |

For user creation, Admin cannot create or assign Super Admin; only Super Admin can grant/revoke the Super Admin role. Admin can manage other users and assign organization/business roles permitted by policy.

## Doubtful Transactions and Notifications

| Method and path | Request / query | Response / access |
| --- | --- | --- |
| `POST /flags` | `{ "entity_type": "invoice|expense", "entity_id", "reason?" }` | CEO and Super Admin. Creates a flag in `flagged`, appends `flag_events`, and notifies the transaction's responsible manager in-app and by push. |
| `GET /flags` | `status`, `entity_type`, `from`, `to`, `limit`, `cursor` | CEO, Admin, Super Admin; managers see only flags assigned to them. |
| `GET /flags/{flag_id}` | None | Flag with transaction summary and event history, subject to scope. |
| `POST /flags/{flag_id}/response` | `{ "response_text" }` | Responsible manager/Asst Manager or authorized Admin/Super Admin; transitions to `reason_submitted`. |
| `POST /flags/{flag_id}/corrected` | `{ "correction_summary" }` | Responsible manager/Asst Manager or authorized Admin/Super Admin; correction must be made through the corresponding invoice/expense update, then transitions to `corrected`. |
| `POST /flags/{flag_id}/resolve` | `{ "resolution_note?" }` | CEO resolves after reason/correction. |
| `POST /flags/{flag_id}/reflag` | `{ "reason" }` | CEO creates a new flag cycle after a resolved flag; history is retained. |
| `GET /notifications` | `unread_only?`, `limit`, `cursor` | Current user's notifications. |
| `POST /notifications/{id}/read` | None | Marks current user's notification read. |
| `PUT /notifications/device-token` | `{ "token", "platform": "ios|android" }` | Registers/updates current user's FCM token. |
| `DELETE /notifications/device-token` | `{ "token" }` | Disables token. |

## Audit Log

| Method and path | Query | Response / access |
| --- | --- | --- |
| `GET /audit-logs` | `business_id?`, `actor_id?`, `entity_type?`, `entity_id?`, `action?`, `from`, `to`, `limit`, `cursor` | Super Admin only. Paginated immutable events with before/after values and timestamp. Admin and all other roles receive `403`. |

Audit entries are generated server-side; clients cannot write or modify them. Sensitive values such as OTP hashes, access/refresh tokens, share tokens, and uploaded file contents are excluded from audit snapshots.

## Role Access Matrix

`SA` Super Admin, `A` Admin, `CEO`, `M` Manager, `AM` Asst Manager. All permissions are additionally limited by selected business scope, except group-level roles can select any active business.

| Capability | SA | A | CEO | M | AM |
| --- |:---:|:---:|:---:|:---:|:---:|
| Read dashboard, customers, invoices, estimates, expenses | Yes | Yes | Yes | Yes | Yes |
| Create/edit invoices, estimates, expenses | Yes | Yes | Yes | Yes | Yes |
| Soft-delete/cancel financial records | Yes | Yes | Yes | Yes, own business policy | Yes, own business policy |
| Configure GST rate history | Yes | Yes | Yes | No | No |
| Configure company details, brick types/rates, master data | Yes | Yes | No | No | No |
| Create/edit/deactivate users | Yes | Yes, no SA grants | No | No | No |
| Flag invoice/expense doubtful | Yes | No | Yes | No | No |
| Respond/correct assigned flagged transaction | Yes | Yes | No | Yes | Yes |
| Resolve/re-flag doubtful transaction | Yes | No | Yes | No | No |
| Read audit log | Yes | No | No | No | No |
| Edit own profile / logout | Yes | Yes | Yes | Yes | Yes |

Admin has broad operational access but no audit-log access. CEO has group-wide business access, GST-rate configuration, and flagging, but not user management or general company/master-data configuration. Super Admin retains all permissions.

## Concurrency, Idempotency, and Validation

- Invoice/estimate create and estimate-conversion endpoints accept `Idempotency-Key`; duplicate retries return the original result, while reusing a key for a different payload returns `409`. Invoice numbering is allocated transactionally per business and FY, with a database uniqueness constraint as the final guard.
- Updates to invoices, estimates, expenses, and configuration should use `If-Match` with an ETag/version. Stale writes return `409 conflict` and do not overwrite newer data.
- Server validates customer ownership, active effective rates, GST selection, allowed discount/override permissions, date ranges, amounts, expense-type-specific fields, advance-recovery balance, and flag transitions.
- OTPs are six digits, expire after five minutes, have a maximum of five verification attempts, and are rate limited per destination. OTP is never returned by API responses or stored in plaintext.
- File uploads have size/type limits and are stored outside the web root. Public share endpoints use high-entropy bearer tokens, store only token hashes, support revocation, and enforce estimate expiration.
- List APIs use allowlisted sort keys and bounded page sizes. Do not expose arbitrary database column sorting or unrestricted audit history.