/**
 * Generado por `openapi-typescript` + `openapi-zod-client --export-schemas`
 * a partir de contracts/openapi.json (Fase 2.5), recortado programáticamente:
 * se descarta el cliente Zodios (`makeApi`/`Zodios`/`createApiClient`) —
 * incompatible con Zod v4 instalado en este proyecto, y de bajo
 * mantenimiento. El propio `--export-schemas` ya expone cada schema
 * individual y un objeto agregado `export const schemas = {...}` —
 * solo se recorta lo que viene DESPUÉS de eso (el array `endpoints` y
 * el cliente Zodios). api-client.ts hace `schemas.EmployeeRead.parse(...)`.
 * NO editar a mano — re-generar desde el openapi.json congelado.
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
};
