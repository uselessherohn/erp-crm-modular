/**
 * Generado por `openapi-typescript` + `openapi-zod-client --export-schemas`
 * a partir de contracts/openapi.json (Fase 2.5), recortado programáticamente:
 * se descarta el cliente Zodios (`makeApi`/`Zodios`/`createApiClient`) —
 * incompatible con Zod v4 instalado en este proyecto, y de bajo
 * mantenimiento/sin uso real en este proyecto (se usa fetch nativo vía
 * src/lib/api-client.ts, no un cliente Zodios). Solo se conserva
 * `export const schemas = { ... }` con los objetos Zod.
 * Do not make direct changes to the file — volver a correr el recorte
 * documentado en LOG_EJECUCION.md tras cualquier regeneración real.
 */
import { z } from "zod";


const CompanyCreate = z
  .object({
    name: z.string().max(200),
    tax_id: z.union([z.string(), z.null()]).optional(),
    timezone: z.string().max(50).optional().default("America/Tegucigalpa"),
    currency_code: z.string().max(3).optional().default("HNL"),
    locale: z.string().max(10).optional().default("es-HN"),
  })
  .passthrough();
const x_internal_api_key = z.union([z.string(), z.null()]).optional();
const CompanyRead = z
  .object({
    name: z.string().max(200),
    tax_id: z.union([z.string(), z.null()]).optional(),
    timezone: z.string().max(50).optional().default("America/Tegucigalpa"),
    currency_code: z.string().max(3).optional().default("HNL"),
    locale: z.string().max(10).optional().default("es-HN"),
    id: z.number().int(),
    is_active: z.boolean(),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const ValidationError = z
  .object({
    loc: z.array(z.union([z.string(), z.number()])),
    msg: z.string(),
    type: z.string(),
    input: z.unknown().optional(),
    ctx: z.object({}).partial().passthrough().optional(),
  })
  .passthrough();
const HTTPValidationError = z
  .object({ detail: z.array(ValidationError) })
  .partial()
  .passthrough();
const LoginRequest = z
  .object({ email: z.string().email(), password: z.string() })
  .passthrough();
const TokenResponse = z
  .object({
    access_token: z.string(),
    refresh_token: z.string(),
    token_type: z.string().optional().default("bearer"),
  })
  .passthrough();
const UserCreate = z
  .object({
    email: z.string().email(),
    full_name: z.string().max(200),
    locale: z.union([z.string(), z.null()]).optional(),
    timezone: z.union([z.string(), z.null()]).optional(),
    password: z.string().min(8),
    role_ids: z.array(z.number().int()).optional(),
  })
  .passthrough();
const UserRead = z
  .object({
    email: z.string().email(),
    full_name: z.string().max(200),
    locale: z.union([z.string(), z.null()]).optional(),
    timezone: z.union([z.string(), z.null()]).optional(),
    id: z.number().int(),
    company_id: z.number().int(),
    is_active: z.boolean(),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const RoleCreate = z
  .object({
    name: z.string().max(100),
    description: z.union([z.string(), z.null()]).optional(),
    permission_ids: z.array(z.number().int()).optional(),
  })
  .passthrough();
const PermissionRead = z
  .object({
    id: z.number().int(),
    code: z.string(),
    description: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const RoleRead = z
  .object({
    name: z.string().max(100),
    description: z.union([z.string(), z.null()]).optional(),
    id: z.number().int(),
    company_id: z.number().int(),
    is_active: z.boolean(),
    permissions: z.array(PermissionRead).optional(),
  })
  .passthrough();
const ContactCreate = z
  .object({
    name: z.string().max(300),
    is_customer: z.boolean().optional().default(false),
    is_vendor: z.boolean().optional().default(false),
    is_patient: z.boolean().optional().default(false),
    is_lead: z.boolean().optional().default(false),
    email: z.union([z.string(), z.null()]).optional(),
    phone: z.union([z.string(), z.null()]).optional(),
    tax_id: z.union([z.string(), z.null()]).optional(),
    address: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const ContactRead = z
  .object({
    name: z.string().max(300),
    is_customer: z.boolean().optional().default(false),
    is_vendor: z.boolean().optional().default(false),
    is_patient: z.boolean().optional().default(false),
    is_lead: z.boolean().optional().default(false),
    email: z.union([z.string(), z.null()]).optional(),
    phone: z.union([z.string(), z.null()]).optional(),
    tax_id: z.union([z.string(), z.null()]).optional(),
    address: z.union([z.string(), z.null()]).optional(),
    id: z.number().int(),
    company_id: z.number().int(),
    is_active: z.boolean(),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const ContactUpdate = z
  .object({
    name: z.union([z.string(), z.null()]),
    is_customer: z.union([z.boolean(), z.null()]),
    is_vendor: z.union([z.boolean(), z.null()]),
    is_patient: z.union([z.boolean(), z.null()]),
    is_lead: z.union([z.boolean(), z.null()]),
    email: z.union([z.string(), z.null()]),
    phone: z.union([z.string(), z.null()]),
    tax_id: z.union([z.string(), z.null()]),
    address: z.union([z.string(), z.null()]),
    is_active: z.union([z.boolean(), z.null()]),
  })
  .partial()
  .passthrough();
const CategoryCreate = z
  .object({
    name: z.string().max(200),
    parent_id: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const CategoryRead = z
  .object({
    name: z.string().max(200),
    parent_id: z.union([z.number(), z.null()]).optional(),
    id: z.number().int(),
    company_id: z.number().int(),
    is_active: z.boolean(),
  })
  .passthrough();
const WarehouseCreate = z
  .object({
    name: z.string().max(200),
    address: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const WarehouseRead = z
  .object({
    name: z.string().max(200),
    address: z.union([z.string(), z.null()]).optional(),
    id: z.number().int(),
    company_id: z.number().int(),
    is_active: z.boolean(),
  })
  .passthrough();
const ProductTypeEnum = z.enum(["facturable", "consumible", "servicio"]);
const ProductCreate = z
  .object({
    sku: z.string().max(100),
    barcode: z.union([z.string(), z.null()]).optional(),
    name: z.string().max(300),
    product_type: ProductTypeEnum,
    category_id: z.union([z.number(), z.null()]).optional(),
    unit_of_measure: z.string().max(20).optional().default("unidad"),
    tracks_lots: z.boolean().optional().default(false),
  })
  .passthrough();
const ProductRead = z
  .object({
    sku: z.string().max(100),
    barcode: z.union([z.string(), z.null()]).optional(),
    name: z.string().max(300),
    product_type: ProductTypeEnum,
    category_id: z.union([z.number(), z.null()]).optional(),
    unit_of_measure: z.string().max(20).optional().default("unidad"),
    tracks_lots: z.boolean().optional().default(false),
    id: z.number().int(),
    company_id: z.number().int(),
    is_active: z.boolean(),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const MovementTypeEnum = z.enum(["entrada", "salida", "ajuste"]);
const StockMovementCreate = z
  .object({
    product_id: z.number().int(),
    warehouse_id: z.number().int(),
    movement_type: MovementTypeEnum,
    quantity: z.union([z.number(), z.string()]),
    lot_number: z.union([z.string(), z.null()]).optional(),
    expiry_date: z.union([z.string(), z.null()]).optional(),
    reference: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const StockMovementRead = z
  .object({
    id: z.number().int(),
    product_id: z.number().int(),
    warehouse_id: z.number().int(),
    lot_id: z.union([z.number(), z.null()]),
    movement_type: z.string(),
    quantity: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    reference: z.union([z.string(), z.null()]),
    correlation_id: z.union([z.string(), z.null()]),
    created_at: z.string().datetime({ offset: true }),
    created_by: z.union([z.number(), z.null()]),
  })
  .passthrough();
const TransferCreate = z
  .object({
    product_id: z.number().int(),
    source_warehouse_id: z.number().int(),
    destination_warehouse_id: z.number().int(),
    quantity: z.union([z.number(), z.string()]),
    lot_number: z.union([z.string(), z.null()]).optional(),
    reference: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const product_id = z.union([z.number(), z.null()]).optional();
const StockLevelRead = z
  .object({
    product_id: z.number().int(),
    warehouse_id: z.number().int(),
    lot_id: z.union([z.number(), z.null()]),
    quantity: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    reserved_quantity: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
  })
  .passthrough();
const PurchaseOrderLineCreate = z
  .object({
    product_id: z.number().int(),
    quantity_ordered: z.union([z.number(), z.string()]),
    unit_cost: z.union([z.number(), z.string()]),
  })
  .passthrough();
const PurchaseOrderCreate = z
  .object({
    vendor_id: z.number().int(),
    warehouse_id: z.number().int(),
    currency_code: z.string().max(3).optional().default("HNL"),
    expected_date: z.union([z.string(), z.null()]).optional(),
    reference: z.union([z.string(), z.null()]).optional(),
    lines: z.array(PurchaseOrderLineCreate).min(1),
  })
  .passthrough();
const PurchaseOrderStatusEnum = z.enum([
  "draft",
  "confirmed",
  "received",
  "closed",
  "cancelled",
]);
const PurchaseOrderLineRead = z
  .object({
    id: z.number().int(),
    product_id: z.number().int(),
    quantity_ordered: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    quantity_received: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    unit_cost: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
  })
  .passthrough();
const PurchaseOrderRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    number: z.string(),
    vendor_id: z.number().int(),
    warehouse_id: z.number().int(),
    status: PurchaseOrderStatusEnum,
    currency_code: z.string(),
    expected_date: z.union([z.string(), z.null()]),
    reference: z.union([z.string(), z.null()]),
    version: z.number().int(),
    created_at: z.string().datetime({ offset: true }),
    lines: z.array(PurchaseOrderLineRead),
  })
  .passthrough();
const ReceiveLineItem = z
  .object({
    line_id: z.number().int(),
    quantity: z.union([z.number(), z.string()]),
  })
  .passthrough();
const ReceivePurchaseOrder = z
  .object({ lines: z.array(ReceiveLineItem).min(1) })
  .passthrough();
const PriceListItemCreate = z
  .object({
    product_id: z.number().int(),
    unit_price: z.union([z.number(), z.string()]),
    min_quantity: z.union([z.number(), z.string()]).optional().default("1"),
  })
  .passthrough();
const PriceListCreate = z
  .object({
    name: z.string().max(200),
    currency_code: z.string().max(3).optional().default("HNL"),
    customer_id: z.union([z.number(), z.null()]).optional(),
    is_default: z.boolean().optional().default(false),
    items: z.array(PriceListItemCreate).optional(),
  })
  .passthrough();
const PriceListItemRead = z
  .object({
    id: z.number().int(),
    product_id: z.number().int(),
    unit_price: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    min_quantity: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
  })
  .passthrough();
const PriceListRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    name: z.string(),
    currency_code: z.string(),
    customer_id: z.union([z.number(), z.null()]),
    is_default: z.boolean(),
    items: z.array(PriceListItemRead),
  })
  .passthrough();
const QuoteLineCreate = z
  .object({
    product_id: z.number().int(),
    quantity: z.union([z.number(), z.string()]),
    unit_price: z.union([z.number(), z.string()]),
  })
  .passthrough();
const QuoteCreate = z
  .object({
    customer_id: z.number().int(),
    price_list_id: z.union([z.number(), z.null()]).optional(),
    currency_code: z.string().max(3).optional().default("HNL"),
    valid_until: z.string(),
    lines: z.array(QuoteLineCreate).min(1),
  })
  .passthrough();
const QuoteStatusEnum = z.enum([
  "draft",
  "sent",
  "accepted",
  "expired",
  "cancelled",
  "converted",
]);
const QuoteLineRead = z
  .object({
    id: z.number().int(),
    product_id: z.number().int(),
    quantity: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    unit_price: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
  })
  .passthrough();
const QuoteRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    number: z.string(),
    customer_id: z.number().int(),
    price_list_id: z.union([z.number(), z.null()]),
    status: QuoteStatusEnum,
    currency_code: z.string(),
    valid_until: z.string(),
    converted_to_order_id: z.union([z.number(), z.null()]),
    version: z.number().int(),
    created_at: z.string().datetime({ offset: true }),
    lines: z.array(QuoteLineRead),
  })
  .passthrough();
const SalesOrderStatusEnum = z.enum([
  "draft",
  "confirmed",
  "en_preparacion",
  "enviado",
  "facturado",
  "cancelado",
]);
const SalesOrderLineRead = z
  .object({
    id: z.number().int(),
    product_id: z.number().int(),
    quantity: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    quantity_shipped: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    unit_price: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
  })
  .passthrough();
const SalesOrderRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    number: z.string(),
    customer_id: z.number().int(),
    warehouse_id: z.number().int(),
    price_list_id: z.union([z.number(), z.null()]),
    status: SalesOrderStatusEnum,
    currency_code: z.string(),
    version: z.number().int(),
    created_at: z.string().datetime({ offset: true }),
    lines: z.array(SalesOrderLineRead),
  })
  .passthrough();
const SalesOrderLineCreate = z
  .object({
    product_id: z.number().int(),
    quantity: z.union([z.number(), z.string()]),
    unit_price: z.union([z.number(), z.string()]),
  })
  .passthrough();
const SalesOrderCreate = z
  .object({
    customer_id: z.number().int(),
    warehouse_id: z.number().int(),
    price_list_id: z.union([z.number(), z.null()]).optional(),
    currency_code: z.string().max(3).optional().default("HNL"),
    lines: z.array(SalesOrderLineCreate).min(1),
  })
  .passthrough();
const ShipLineItem = z
  .object({
    line_id: z.number().int(),
    quantity: z.union([z.number(), z.string()]),
  })
  .passthrough();
const ShipSalesOrder = z
  .object({ lines: z.array(ShipLineItem).min(1) })
  .passthrough();
const AccountTypeEnum = z.enum([
  "receivable",
  "payable",
  "income",
  "tax",
  "cash_bank",
  "adjustment",
]);
const AccountCreate = z
  .object({
    code: z.string().max(30),
    name: z.string().max(200),
    account_type: AccountTypeEnum,
    is_default: z.boolean().optional().default(false),
  })
  .passthrough();
const AccountRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    code: z.string(),
    name: z.string(),
    account_type: AccountTypeEnum,
    is_default: z.boolean(),
    is_active: z.boolean(),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const DocumentTypeEnum = z.enum([
  "sales_invoice",
  "purchase_invoice",
  "sales_credit_note",
  "sales_debit_note",
  "purchase_credit_note",
  "purchase_debit_note",
  "payment_received",
  "payment_made",
]);
const DocumentAccountMappingCreate = z
  .object({
    document_type: DocumentTypeEnum,
    role: AccountTypeEnum,
    account_id: z.number().int(),
  })
  .passthrough();
const DocumentAccountMappingRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    document_type: DocumentTypeEnum,
    role: AccountTypeEnum,
    account_id: z.number().int(),
  })
  .passthrough();
const TaxRateCreate = z
  .object({
    name: z.string().max(100),
    rate: z.union([z.number(), z.string()]),
    is_default: z.boolean().optional().default(false),
  })
  .passthrough();
const TaxRateRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    name: z.string(),
    rate: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    is_default: z.boolean(),
    is_active: z.boolean(),
  })
  .passthrough();
const DirectionEnum = z.enum(["sale", "purchase"]);
const InvoiceLineCreate = z
  .object({
    description: z.string().max(300),
    quantity: z.union([z.number(), z.string()]).optional().default("1"),
    unit_price: z.union([z.number(), z.string()]),
    tax_rate_id: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const InvoiceCreate = z
  .object({
    direction: DirectionEnum,
    contact_id: z.number().int(),
    currency_code: z.string().max(3).optional().default("HNL"),
    issue_date: z.string(),
    due_date: z.union([z.string(), z.null()]).optional(),
    source_document_type: z.union([z.string(), z.null()]).optional(),
    source_document_id: z.union([z.number(), z.null()]).optional(),
    lines: z.array(InvoiceLineCreate).min(1),
  })
  .passthrough();
const InvoiceStatusEnum = z.enum([
  "draft",
  "posted",
  "partially_paid",
  "paid",
  "cancelled",
]);
const InvoiceLineRead = z
  .object({
    id: z.number().int(),
    description: z.string(),
    quantity: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    unit_price: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    tax_rate_id: z.union([z.number(), z.null()]),
    line_subtotal: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    line_tax: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    line_total: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
  })
  .passthrough();
const InvoiceRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    number: z.string(),
    direction: DirectionEnum,
    contact_id: z.number().int(),
    status: InvoiceStatusEnum,
    currency_code: z.string(),
    issue_date: z.string(),
    due_date: z.union([z.string(), z.null()]),
    subtotal: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    tax_amount: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    total: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    balance_due: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    source_document_type: z.union([z.string(), z.null()]),
    source_document_id: z.union([z.number(), z.null()]),
    journal_entry_id: z.union([z.number(), z.null()]),
    version: z.number().int(),
    created_at: z.string().datetime({ offset: true }),
    lines: z.array(InvoiceLineRead),
  })
  .passthrough();
const NoteTypeEnum = z.enum(["credit", "debit"]);
const CreditDebitNoteLineCreate = z
  .object({
    description: z.string().max(300),
    quantity: z.union([z.number(), z.string()]).optional().default("1"),
    unit_price: z.union([z.number(), z.string()]),
    tax_rate_id: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const CreditDebitNoteCreate = z
  .object({
    note_type: NoteTypeEnum,
    direction: DirectionEnum,
    contact_id: z.number().int(),
    invoice_id: z.union([z.number(), z.null()]).optional(),
    reason: z.string().max(500),
    issue_date: z.string(),
    lines: z.array(CreditDebitNoteLineCreate).min(1),
  })
  .passthrough();
const NoteStatusEnum = z.enum(["draft", "posted", "cancelled"]);
const CreditDebitNoteLineRead = z
  .object({
    id: z.number().int(),
    description: z.string(),
    quantity: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    unit_price: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    tax_rate_id: z.union([z.number(), z.null()]),
    line_subtotal: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    line_tax: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    line_total: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
  })
  .passthrough();
const CreditDebitNoteRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    number: z.string(),
    note_type: NoteTypeEnum,
    direction: DirectionEnum,
    contact_id: z.number().int(),
    invoice_id: z.union([z.number(), z.null()]),
    reason: z.string(),
    status: NoteStatusEnum,
    issue_date: z.string(),
    subtotal: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    tax_amount: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    total: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    journal_entry_id: z.union([z.number(), z.null()]),
    version: z.number().int(),
    created_at: z.string().datetime({ offset: true }),
    lines: z.array(CreditDebitNoteLineRead),
  })
  .passthrough();
const PaymentMethodEnum = z.enum([
  "cash",
  "bank_transfer",
  "card",
  "check",
  "other",
]);
const PaymentAllocationCreate = z
  .object({
    invoice_id: z.number().int(),
    amount_applied: z.union([z.number(), z.string()]),
  })
  .passthrough();
const PaymentCreate = z
  .object({
    direction: DirectionEnum,
    contact_id: z.number().int(),
    payment_date: z.string(),
    method: PaymentMethodEnum,
    amount: z.union([z.number(), z.string()]),
    reference: z.union([z.string(), z.null()]).optional(),
    allocations: z.array(PaymentAllocationCreate).optional(),
  })
  .passthrough();
const PaymentStatusEnum = z.enum(["draft", "posted", "cancelled"]);
const PaymentAllocationRead = z
  .object({
    id: z.number().int(),
    invoice_id: z.number().int(),
    amount_applied: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
  })
  .passthrough();
const PaymentRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    number: z.string(),
    direction: DirectionEnum,
    contact_id: z.number().int(),
    payment_date: z.string(),
    method: PaymentMethodEnum,
    amount: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    reference: z.union([z.string(), z.null()]),
    status: PaymentStatusEnum,
    journal_entry_id: z.union([z.number(), z.null()]),
    version: z.number().int(),
    created_at: z.string().datetime({ offset: true }),
    allocations: z.array(PaymentAllocationRead),
  })
  .passthrough();
const CreditStatusRead = z
  .object({
    contact_id: z.number().int(),
    is_blocked: z.boolean(),
    has_overdue_invoices: z.boolean(),
    credit_limit: z.union([z.string(), z.null()]),
    outstanding_balance: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    credit_exceeded: z.boolean(),
  })
  .passthrough();
const StageCreate = z
  .object({
    name: z.string().max(100),
    sort_order: z.number().int().optional().default(0),
    is_won: z.boolean().optional().default(false),
    is_lost: z.boolean().optional().default(false),
  })
  .passthrough();
const StageRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    name: z.string(),
    sort_order: z.number().int(),
    is_won: z.boolean(),
    is_lost: z.boolean(),
    is_active: z.boolean(),
  })
  .passthrough();
const OpportunityCreate = z
  .object({
    contact_id: z.number().int(),
    stage_id: z.number().int(),
    name: z.string().max(300),
    amount: z.union([z.number(), z.string(), z.null()]).optional(),
    currency_code: z.string().max(3).optional().default("HNL"),
    expected_close_date: z.union([z.string(), z.null()]).optional(),
    owner_user_id: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const OpportunityStatusEnum = z.enum(["open", "won", "lost"]);
const OpportunityRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    contact_id: z.number().int(),
    stage_id: z.number().int(),
    owner_user_id: z.union([z.number(), z.null()]),
    name: z.string(),
    amount: z.union([z.string(), z.null()]),
    currency_code: z.string(),
    expected_close_date: z.union([z.string(), z.null()]),
    status: OpportunityStatusEnum,
    closed_at: z.union([z.string(), z.null()]),
    lost_reason: z.union([z.string(), z.null()]),
    version: z.number().int(),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const OpportunityMoveStage = z
  .object({ stage_id: z.number().int() })
  .passthrough();
const OpportunityCloseLost = z
  .object({ lost_reason: z.union([z.string(), z.null()]) })
  .partial()
  .passthrough();
const ActivityTypeEnum = z.enum(["call", "email", "meeting", "note", "task"]);
const ActivityCreate = z
  .object({
    contact_id: z.number().int(),
    opportunity_id: z.union([z.number(), z.null()]).optional(),
    activity_type: ActivityTypeEnum,
    subject: z.string().max(300),
    notes: z.union([z.string(), z.null()]).optional(),
    due_date: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const ActivityRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    contact_id: z.number().int(),
    opportunity_id: z.union([z.number(), z.null()]),
    activity_type: ActivityTypeEnum,
    subject: z.string(),
    notes: z.union([z.string(), z.null()]),
    due_date: z.union([z.string(), z.null()]),
    completed_at: z.union([z.string(), z.null()]),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const DepartmentCreate = z
  .object({
    name: z.string().max(150),
    parent_department_id: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const DepartmentRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    name: z.string(),
    parent_department_id: z.union([z.number(), z.null()]),
  })
  .passthrough();
const PositionCreate = z
  .object({ title: z.string().max(150), department_id: z.number().int() })
  .passthrough();
const PositionRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    title: z.string(),
    department_id: z.number().int(),
  })
  .passthrough();
const EmployeeCreate = z
  .object({
    first_name: z.string().max(150),
    last_name: z.string().max(150),
    email: z.union([z.string(), z.null()]).optional(),
    phone: z.union([z.string(), z.null()]).optional(),
    national_id: z.union([z.string(), z.null()]).optional(),
    position_id: z.union([z.number(), z.null()]).optional(),
    manager_employee_id: z.union([z.number(), z.null()]).optional(),
    hire_date: z.string(),
    salary: z.union([z.number(), z.string(), z.null()]).optional(),
    user_id: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const EmployeeStatusEnum = z.enum(["active", "terminated"]);
const EmployeeRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    user_id: z.union([z.number(), z.null()]),
    first_name: z.string(),
    last_name: z.string(),
    email: z.union([z.string(), z.null()]),
    phone: z.union([z.string(), z.null()]),
    national_id: z.union([z.string(), z.null()]),
    position_id: z.union([z.number(), z.null()]),
    manager_employee_id: z.union([z.number(), z.null()]),
    hire_date: z.string(),
    termination_date: z.union([z.string(), z.null()]),
    status: EmployeeStatusEnum,
    salary: z.union([z.string(), z.null()]),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const EmployeeTerminate = z
  .object({ termination_date: z.string() })
  .passthrough();
const ClinicalRecordEntryTypeEnum = z.enum([
  "antecedent",
  "allergy",
  "diagnosis",
  "note",
]);
const ClinicalRecordEntryCreate = z
  .object({
    patient_contact_id: z.number().int(),
    entry_type: ClinicalRecordEntryTypeEnum,
    content: z.string().min(1),
    previous_entry_id: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const ClinicalRecordEntryRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    patient_contact_id: z.number().int(),
    entry_type: ClinicalRecordEntryTypeEnum,
    content: z.string(),
    previous_entry_id: z.union([z.number(), z.null()]),
    author_user_id: z.number().int(),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const AppointmentCreate = z
  .object({
    patient_contact_id: z.number().int(),
    professional_user_id: z.number().int(),
    scheduled_start: z.string().datetime({ offset: true }),
    scheduled_end: z.string().datetime({ offset: true }),
    reason: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const AppointmentStatusEnum = z.enum([
  "scheduled",
  "confirmed",
  "completed",
  "cancelled",
  "no_show",
]);
const AppointmentRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    patient_contact_id: z.number().int(),
    professional_user_id: z.number().int(),
    scheduled_start: z.string().datetime({ offset: true }),
    scheduled_end: z.string().datetime({ offset: true }),
    status: AppointmentStatusEnum,
    reason: z.union([z.string(), z.null()]),
    cancellation_reason: z.union([z.string(), z.null()]),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const AppointmentReschedule = z
  .object({
    scheduled_start: z.string().datetime({ offset: true }),
    scheduled_end: z.string().datetime({ offset: true }),
    reason: z.string().min(1).max(500),
  })
  .passthrough();
const AppointmentCancel = z
  .object({ cancellation_reason: z.string().min(1).max(500) })
  .passthrough();
const ConsultationRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    appointment_id: z.number().int(),
    patient_contact_id: z.number().int(),
    professional_user_id: z.number().int(),
    physical_exam: z.union([z.string(), z.null()]),
    diagnosis_cie10: z.union([z.string(), z.null()]),
    diagnosis_text: z.union([z.string(), z.null()]),
    treatment_plan: z.union([z.string(), z.null()]),
    previous_consultation_id: z.union([z.number(), z.null()]),
    superseded_by_id: z.union([z.number(), z.null()]),
    created_by: z.number().int(),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const ConsultationCreate = z
  .object({
    appointment_id: z.number().int(),
    physical_exam: z.union([z.string(), z.null()]).optional(),
    diagnosis_cie10: z.union([z.string(), z.null()]).optional(),
    diagnosis_text: z.union([z.string(), z.null()]).optional(),
    treatment_plan: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const ConsultationCorrect = z
  .object({
    physical_exam: z.union([z.string(), z.null()]),
    diagnosis_cie10: z.union([z.string(), z.null()]),
    diagnosis_text: z.union([z.string(), z.null()]),
    treatment_plan: z.union([z.string(), z.null()]),
  })
  .partial()
  .passthrough();
const PrescriptionLineCreate = z
  .object({
    medication_name: z.string().min(1).max(300),
    dosage: z.string().min(1).max(100),
    route: z.string().min(1).max(100),
    frequency: z.string().min(1).max(100),
    duration: z.string().min(1).max(100),
  })
  .passthrough();
const PrescriptionCreate = z
  .object({
    consultation_id: z.number().int(),
    notes: z.union([z.string(), z.null()]).optional(),
    lines: z.array(PrescriptionLineCreate).min(1),
  })
  .passthrough();
const PrescriptionDispensingStatusEnum = z.enum([
  "not_applicable",
  "pending",
  "dispensed",
]);
const PrescriptionLineRead = z
  .object({
    id: z.number().int(),
    medication_name: z.string(),
    dosage: z.string(),
    route: z.string(),
    frequency: z.string(),
    duration: z.string(),
    dispensing_status: PrescriptionDispensingStatusEnum,
  })
  .passthrough();
const PrescriptionRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    consultation_id: z.number().int(),
    patient_contact_id: z.number().int(),
    professional_user_id: z.number().int(),
    notes: z.union([z.string(), z.null()]),
    voided_at: z.union([z.string(), z.null()]),
    void_reason: z.union([z.string(), z.null()]),
    issued_at: z.string().datetime({ offset: true }),
    created_by: z.number().int(),
    lines: z.array(PrescriptionLineRead),
  })
  .passthrough();
const PrescriptionVoid = z
  .object({ void_reason: z.string().min(1).max(500) })
  .passthrough();
const LabOrderTestRequest = z
  .object({ test_name: z.string().min(1).max(300) })
  .passthrough();
const LabOrderCreate = z
  .object({
    consultation_id: z.number().int(),
    tests: z.array(LabOrderTestRequest).min(1),
  })
  .passthrough();
const LabOrderStatusEnum = z.enum(["ordered", "completed", "cancelled"]);
const LabOrderTestStatusEnum = z.enum(["pending", "resulted"]);
const LabOrderTestRead = z
  .object({
    id: z.number().int(),
    test_name: z.string(),
    status: LabOrderTestStatusEnum,
    result_value: z.union([z.string(), z.null()]),
    result_unit: z.union([z.string(), z.null()]),
    reference_range_text: z.union([z.string(), z.null()]),
    is_critical: z.boolean(),
    resulted_at: z.union([z.string(), z.null()]),
    resulted_by: z.union([z.number(), z.null()]),
  })
  .passthrough();
const LabOrderRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    consultation_id: z.number().int(),
    patient_contact_id: z.number().int(),
    professional_user_id: z.number().int(),
    status: LabOrderStatusEnum,
    ordered_at: z.string().datetime({ offset: true }),
    created_by: z.number().int(),
    tests: z.array(LabOrderTestRead),
  })
  .passthrough();
const LabOrderTestResult = z
  .object({
    result_value: z.string().min(1).max(300),
    result_unit: z.union([z.string(), z.null()]).optional(),
    reference_range_text: z.union([z.string(), z.null()]).optional(),
    is_critical: z.boolean().optional().default(false),
  })
  .passthrough();
const Body_upload_lab_order_test_attachment_medical_lab_order_tests__lab_order_test_id__attachments_post =
  z.object({ file: z.string() }).passthrough();
const AttachmentRead = z
  .object({
    id: z.number().int(),
    entity_type: z.string(),
    entity_id: z.number().int(),
    filename: z.string(),
    mime_type: z.string(),
    uploaded_by: z.number().int(),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const TeleconsultationSessionCreate = z
  .object({ appointment_id: z.number().int() })
  .passthrough();
const TeleconsultationStatusEnum = z.enum([
  "scheduled",
  "active",
  "ended",
  "cancelled",
]);
const TeleconsultationSessionRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    appointment_id: z.number().int(),
    patient_contact_id: z.number().int(),
    professional_user_id: z.number().int(),
    provider: z.string(),
    room_external_id: z.string(),
    join_url: z.string(),
    status: TeleconsultationStatusEnum,
    started_at: z.union([z.string(), z.null()]),
    ended_at: z.union([z.string(), z.null()]),
    created_at: z.string().datetime({ offset: true }),
    created_by: z.number().int(),
  })
  .passthrough();
const MedicalBillingCreate = z
  .object({
    consultation_id: z.number().int(),
    amount: z.union([z.number(), z.string()]),
    currency_code: z.string().max(3).optional().default("HNL"),
    issue_date: z.string(),
    tax_rate_id: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const MedicalBillingModeEnum = z.enum(["accounting_invoice", "simple_receipt"]);
const MedicalBillingStatusEnum = z.enum(["issued", "cancelled"]);
const MedicalBillingRecordRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    consultation_id: z.number().int(),
    patient_contact_id: z.number().int(),
    professional_user_id: z.number().int(),
    billing_mode: MedicalBillingModeEnum,
    status: MedicalBillingStatusEnum,
    amount: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    currency_code: z.string(),
    issue_date: z.string(),
    invoice_id: z.union([z.number(), z.null()]),
    receipt_number: z.union([z.string(), z.null()]),
    cancelled_at: z.union([z.string(), z.null()]),
    cancel_reason: z.union([z.string(), z.null()]),
    created_at: z.string().datetime({ offset: true }),
    created_by: z.number().int(),
  })
  .passthrough();
const MedicalBillingCancel = z
  .object({ cancel_reason: z.string().min(1).max(500) })
  .passthrough();
const PatientMessageSenderRoleEnum = z.enum(["professional", "patient"]);
const PatientMessageCreate = z
  .object({
    patient_contact_id: z.number().int(),
    professional_user_id: z.number().int(),
    sender_role: PatientMessageSenderRoleEnum,
    body: z.string().min(1).max(2000),
  })
  .passthrough();
const PatientMessageRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    patient_contact_id: z.number().int(),
    professional_user_id: z.number().int(),
    sender_role: PatientMessageSenderRoleEnum,
    author_user_id: z.number().int(),
    body: z.string(),
    read_at: z.union([z.string(), z.null()]),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const NotificationTemplateCreate = z
  .object({
    code: z.string().min(1).max(100),
    subject_template: z.string().min(1).max(300),
    body_template: z.string().min(1),
  })
  .passthrough();
const NotificationTemplateRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    code: z.string(),
    subject_template: z.string(),
    body_template: z.string(),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const NotificationTemplateUpdate = z
  .object({
    subject_template: z.union([z.string(), z.null()]),
    body_template: z.union([z.string(), z.null()]),
  })
  .partial()
  .passthrough();
const NotificationChannelEnum = z.enum(["in_app", "email"]);
const NotificationSend = z
  .object({
    recipient_user_id: z.number().int(),
    channel: NotificationChannelEnum.optional(),
    title: z.union([z.string(), z.null()]).optional(),
    body: z.union([z.string(), z.null()]).optional(),
    template_code: z.union([z.string(), z.null()]).optional(),
    context: z.record(z.string(), z.string()).optional(),
  })
  .passthrough();
const NotificationRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    recipient_user_id: z.number().int(),
    channel: NotificationChannelEnum,
    title: z.string(),
    body: z.string(),
    template_code: z.union([z.string(), z.null()]),
    email_status: z.union([z.string(), z.null()]),
    read_at: z.union([z.string(), z.null()]),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const PageCreate = z
  .object({
    slug: z
      .string()
      .max(150)
      .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/),
    title: z.string().max(300),
    content: z.string().optional().default(""),
  })
  .passthrough();
const PageRead = z
  .object({
    slug: z
      .string()
      .max(150)
      .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/),
    title: z.string().max(300),
    content: z.string().optional().default(""),
    id: z.number().int(),
    company_id: z.number().int(),
    status: z.string(),
    published_at: z.union([z.string(), z.null()]),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const PageUpdate = z
  .object({
    title: z.union([z.string(), z.null()]),
    content: z.union([z.string(), z.null()]),
  })
  .partial()
  .passthrough();
const FormSubmissionRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    page_id: z.union([z.number(), z.null()]),
    form_name: z.string(),
    payload: z.object({}).partial().passthrough(),
    contact_id: z.number().int(),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const FormSubmissionCreate = z
  .object({
    form_name: z.string().max(100),
    page_id: z.union([z.number(), z.null()]).optional(),
    name: z.string().max(300),
    email: z.union([z.string(), z.null()]).optional(),
    phone: z.union([z.string(), z.null()]).optional(),
    message: z.union([z.string(), z.null()]).optional(),
    extra: z.object({}).partial().passthrough().optional(),
  })
  .passthrough();
const EcommerceSettingsCreated = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    default_warehouse_id: z.union([z.number(), z.null()]),
    default_price_list_id: z.union([z.number(), z.null()]),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
    webhook_secret: z.string(),
  })
  .passthrough();
const EcommerceSettingsRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    default_warehouse_id: z.union([z.number(), z.null()]),
    default_price_list_id: z.union([z.number(), z.null()]),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const EcommerceSettingsUpdate = z
  .object({
    default_warehouse_id: z.union([z.number(), z.null()]),
    default_price_list_id: z.union([z.number(), z.null()]),
  })
  .partial()
  .passthrough();
const CatalogItem = z
  .object({
    product_id: z.number().int(),
    sku: z.string(),
    name: z.string(),
    unit_price: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
  })
  .passthrough();
const CartItemRead = z
  .object({
    id: z.number().int(),
    product_id: z.number().int(),
    quantity: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    unit_price_snapshot: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
  })
  .passthrough();
const CartCreated = z
  .object({
    id: z.number().int(),
    status: z.string(),
    currency_code: z.string(),
    sales_order_id: z.union([z.number(), z.null()]),
    items: z.array(CartItemRead),
    session_token: z.string(),
  })
  .passthrough();
const CartRead = z
  .object({
    id: z.number().int(),
    status: z.string(),
    currency_code: z.string(),
    sales_order_id: z.union([z.number(), z.null()]),
    items: z.array(CartItemRead),
  })
  .passthrough();
const AddCartItem = z
  .object({
    product_id: z.number().int(),
    quantity: z.union([z.number(), z.string()]),
  })
  .passthrough();
const CheckoutRequest = z
  .object({
    name: z.string().max(300),
    email: z.string().max(255),
    phone: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const CheckoutResult = z
  .object({
    sales_order_id: z.number().int(),
    sales_order_number: z.string(),
    status: z.string(),
    total_lines: z.number().int(),
  })
  .passthrough();
const MetricInfo = z
  .object({ key: z.string(), label: z.string(), columns: z.array(z.string()) })
  .passthrough();
const MetricDataResult = z
  .object({
    key: z.string(),
    columns: z.array(z.string()),
    rows: z.array(z.object({}).partial().passthrough()),
  })
  .passthrough();
const DashboardWidget = z
  .object({
    widget_type: z
      .string()
      .regex(/^(table|metric)$/)
      .optional()
      .default("table"),
    metric_key: z.string(),
    title: z.string().max(200),
  })
  .passthrough();
const DashboardCreate = z
  .object({
    name: z.string().max(200),
    widgets: z.array(DashboardWidget).optional(),
  })
  .passthrough();
const DashboardRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    name: z.string(),
    owner_user_id: z.union([z.number(), z.null()]),
    widgets: z.array(DashboardWidget),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const DashboardUpdate = z
  .object({
    name: z.union([z.string(), z.null()]),
    widgets: z.union([z.array(DashboardWidget), z.null()]),
  })
  .partial()
  .passthrough();
const DispensationLineRequest = z
  .object({
    product_id: z.number().int(),
    quantity: z.union([z.number(), z.string()]),
  })
  .passthrough();
const DispensationOrderCreate = z
  .object({
    warehouse_id: z.number().int(),
    patient_contact_id: z.number().int(),
    prescription_id: z.union([z.number(), z.null()]).optional(),
    walk_in_reference: z.union([z.string(), z.null()]).optional(),
    allergy_check_notes: z.union([z.string(), z.null()]).optional(),
    payment_method: z.union([z.string(), z.null()]).optional(),
    amount_charged: z.union([z.number(), z.string(), z.null()]).optional(),
    lines: z.array(DispensationLineRequest).min(1),
  })
  .passthrough();
const AllergyCheckSourceEnum = z.enum(["medical_record", "form"]);
const DispensationStatusEnum = z.enum(["dispensed", "voided"]);
const DispensationLineRead = z
  .object({
    id: z.number().int(),
    product_id: z.number().int(),
    lot_id: z.union([z.number(), z.null()]),
    quantity: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
  })
  .passthrough();
const DispensationOrderRead = z
  .object({
    id: z.number().int(),
    company_id: z.number().int(),
    warehouse_id: z.number().int(),
    patient_contact_id: z.number().int(),
    dispensed_by: z.number().int(),
    document_number: z.string(),
    prescription_id: z.union([z.number(), z.null()]),
    walk_in_reference: z.union([z.string(), z.null()]),
    allergy_check_source: AllergyCheckSourceEnum,
    allergy_check_notes: z.union([z.string(), z.null()]),
    payment_method: z.union([z.string(), z.null()]),
    amount_charged: z.union([z.string(), z.null()]),
    status: DispensationStatusEnum,
    voided_at: z.union([z.string(), z.null()]),
    void_reason: z.union([z.string(), z.null()]),
    dispensed_at: z.string().datetime({ offset: true }),
    lines: z.array(DispensationLineRead),
  })
  .passthrough();
const DispensationVoid = z
  .object({ void_reason: z.string().min(1).max(500) })
  .passthrough();
const ControlledSubstanceMark = z
  .object({ product_id: z.number().int() })
  .passthrough();
const ControlledSubstanceProductRead = z
  .object({
    id: z.number().int(),
    product_id: z.number().int(),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const ControlledSubstanceLogEntryRead = z
  .object({
    id: z.number().int(),
    dispensation_line_id: z.number().int(),
    product_id: z.number().int(),
    patient_contact_id: z.number().int(),
    dispensed_by: z.number().int(),
    quantity: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const ProductActiveIngredientSet = z
  .object({
    product_id: z.number().int(),
    active_ingredient: z.string().min(1).max(200),
  })
  .passthrough();
const ProductActiveIngredientRead = z
  .object({
    id: z.number().int(),
    product_id: z.number().int(),
    active_ingredient: z.string(),
  })
  .passthrough();
const InteractionCheckRequest = z
  .object({ product_ids: z.array(z.number().int()).min(2) })
  .passthrough();
const InteractionSeverityEnum = z.enum(["moderate", "major"]);
const InteractionWarning = z
  .object({
    product_id_a: z.number().int(),
    product_id_b: z.number().int(),
    ingredient_a: z.string(),
    ingredient_b: z.string(),
    severity: InteractionSeverityEnum,
    description: z.string(),
  })
  .passthrough();
const InteractionCheckResult = z
  .object({
    warnings: z.array(InteractionWarning),
    unchecked_product_ids: z.array(z.number().int()),
  })
  .passthrough();
const InsuranceProviderCreate = z
  .object({
    contact_id: z.number().int(),
    default_coverage_percentage: z
      .union([z.number(), z.string(), z.null()])
      .optional(),
  })
  .passthrough();
const InsuranceProviderRead = z
  .object({
    id: z.number().int(),
    contact_id: z.number().int(),
    default_coverage_percentage: z.union([z.string(), z.null()]),
    is_active: z.boolean(),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const PatientInsurancePolicyCreate = z
  .object({
    patient_contact_id: z.number().int(),
    insurance_provider_id: z.number().int(),
    policy_number: z.string().min(1).max(100),
    coverage_percentage: z.union([z.number(), z.string()]),
  })
  .passthrough();
const PatientInsurancePolicyRead = z
  .object({
    id: z.number().int(),
    patient_contact_id: z.number().int(),
    insurance_provider_id: z.number().int(),
    policy_number: z.string(),
    coverage_percentage: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    is_active: z.boolean(),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const InsuranceClaimCreate = z
  .object({
    dispensation_order_id: z.number().int(),
    insurance_provider_id: z.number().int(),
    amount_total: z.union([z.number(), z.string()]),
    amount_patient_copay: z.union([z.number(), z.string()]),
    amount_claimed_insurer: z.union([z.number(), z.string()]),
  })
  .passthrough();
const InsuranceClaimStatusEnum = z.enum([
  "pending",
  "submitted",
  "approved",
  "paid",
  "rejected",
]);
const InsuranceClaimRead = z
  .object({
    id: z.number().int(),
    dispensation_order_id: z.number().int(),
    insurance_provider_id: z.number().int(),
    patient_contact_id: z.number().int(),
    claim_number: z.string(),
    amount_total: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    amount_patient_copay: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    amount_claimed_insurer: z.string().regex(/^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$/),
    status: InsuranceClaimStatusEnum,
    billing_mode: z.union([z.string(), z.null()]),
    invoice_id: z.union([z.number(), z.null()]),
    payment_id: z.union([z.number(), z.null()]),
    rejection_reason: z.union([z.string(), z.null()]),
    created_at: z.string().datetime({ offset: true }),
    submitted_at: z.union([z.string(), z.null()]),
    approved_at: z.union([z.string(), z.null()]),
    paid_at: z.union([z.string(), z.null()]),
    rejected_at: z.union([z.string(), z.null()]),
  })
  .passthrough();
const InsuranceClaimReject = z
  .object({ rejection_reason: z.string().min(1).max(500) })
  .passthrough();
const InsuranceClaimPay = z
  .object({ amount_paid: z.union([z.number(), z.string(), z.null()]) })
  .partial()
  .passthrough();

export const schemas = {
  CompanyCreate,
  x_internal_api_key,
  CompanyRead,
  ValidationError,
  HTTPValidationError,
  LoginRequest,
  TokenResponse,
  UserCreate,
  UserRead,
  RoleCreate,
  PermissionRead,
  RoleRead,
  ContactCreate,
  ContactRead,
  ContactUpdate,
  CategoryCreate,
  CategoryRead,
  WarehouseCreate,
  WarehouseRead,
  ProductTypeEnum,
  ProductCreate,
  ProductRead,
  MovementTypeEnum,
  StockMovementCreate,
  StockMovementRead,
  TransferCreate,
  product_id,
  StockLevelRead,
  PurchaseOrderLineCreate,
  PurchaseOrderCreate,
  PurchaseOrderStatusEnum,
  PurchaseOrderLineRead,
  PurchaseOrderRead,
  ReceiveLineItem,
  ReceivePurchaseOrder,
  PriceListItemCreate,
  PriceListCreate,
  PriceListItemRead,
  PriceListRead,
  QuoteLineCreate,
  QuoteCreate,
  QuoteStatusEnum,
  QuoteLineRead,
  QuoteRead,
  SalesOrderStatusEnum,
  SalesOrderLineRead,
  SalesOrderRead,
  SalesOrderLineCreate,
  SalesOrderCreate,
  ShipLineItem,
  ShipSalesOrder,
  AccountTypeEnum,
  AccountCreate,
  AccountRead,
  DocumentTypeEnum,
  DocumentAccountMappingCreate,
  DocumentAccountMappingRead,
  TaxRateCreate,
  TaxRateRead,
  DirectionEnum,
  InvoiceLineCreate,
  InvoiceCreate,
  InvoiceStatusEnum,
  InvoiceLineRead,
  InvoiceRead,
  NoteTypeEnum,
  CreditDebitNoteLineCreate,
  CreditDebitNoteCreate,
  NoteStatusEnum,
  CreditDebitNoteLineRead,
  CreditDebitNoteRead,
  PaymentMethodEnum,
  PaymentAllocationCreate,
  PaymentCreate,
  PaymentStatusEnum,
  PaymentAllocationRead,
  PaymentRead,
  CreditStatusRead,
  StageCreate,
  StageRead,
  OpportunityCreate,
  OpportunityStatusEnum,
  OpportunityRead,
  OpportunityMoveStage,
  OpportunityCloseLost,
  ActivityTypeEnum,
  ActivityCreate,
  ActivityRead,
  DepartmentCreate,
  DepartmentRead,
  PositionCreate,
  PositionRead,
  EmployeeCreate,
  EmployeeStatusEnum,
  EmployeeRead,
  EmployeeTerminate,
  ClinicalRecordEntryTypeEnum,
  ClinicalRecordEntryCreate,
  ClinicalRecordEntryRead,
  AppointmentCreate,
  AppointmentStatusEnum,
  AppointmentRead,
  AppointmentReschedule,
  AppointmentCancel,
  ConsultationRead,
  ConsultationCreate,
  ConsultationCorrect,
  PrescriptionLineCreate,
  PrescriptionCreate,
  PrescriptionDispensingStatusEnum,
  PrescriptionLineRead,
  PrescriptionRead,
  PrescriptionVoid,
  LabOrderTestRequest,
  LabOrderCreate,
  LabOrderStatusEnum,
  LabOrderTestStatusEnum,
  LabOrderTestRead,
  LabOrderRead,
  LabOrderTestResult,
  Body_upload_lab_order_test_attachment_medical_lab_order_tests__lab_order_test_id__attachments_post,
  AttachmentRead,
  TeleconsultationSessionCreate,
  TeleconsultationStatusEnum,
  TeleconsultationSessionRead,
  MedicalBillingCreate,
  MedicalBillingModeEnum,
  MedicalBillingStatusEnum,
  MedicalBillingRecordRead,
  MedicalBillingCancel,
  PatientMessageSenderRoleEnum,
  PatientMessageCreate,
  PatientMessageRead,
  NotificationTemplateCreate,
  NotificationTemplateRead,
  NotificationTemplateUpdate,
  NotificationChannelEnum,
  NotificationSend,
  NotificationRead,
  PageCreate,
  PageRead,
  PageUpdate,
  FormSubmissionRead,
  FormSubmissionCreate,
  EcommerceSettingsCreated,
  EcommerceSettingsRead,
  EcommerceSettingsUpdate,
  CatalogItem,
  CartItemRead,
  CartCreated,
  CartRead,
  AddCartItem,
  CheckoutRequest,
  CheckoutResult,
  MetricInfo,
  MetricDataResult,
  DashboardWidget,
  DashboardCreate,
  DashboardRead,
  DashboardUpdate,
  DispensationLineRequest,
  DispensationOrderCreate,
  AllergyCheckSourceEnum,
  DispensationStatusEnum,
  DispensationLineRead,
  DispensationOrderRead,
  DispensationVoid,
  ControlledSubstanceMark,
  ControlledSubstanceProductRead,
  ControlledSubstanceLogEntryRead,
  ProductActiveIngredientSet,
  ProductActiveIngredientRead,
  InteractionCheckRequest,
  InteractionSeverityEnum,
  InteractionWarning,
  InteractionCheckResult,
  InsuranceProviderCreate,
  InsuranceProviderRead,
  PatientInsurancePolicyCreate,
  PatientInsurancePolicyRead,
  InsuranceClaimCreate,
  InsuranceClaimStatusEnum,
  InsuranceClaimRead,
  InsuranceClaimReject,
  InsuranceClaimPay,
};

