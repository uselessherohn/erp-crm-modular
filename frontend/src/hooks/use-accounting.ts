import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, schemas } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";
import type { z } from "zod";

type AccountRead = components["schemas"]["AccountRead"];
type DocumentAccountMappingRead = components["schemas"]["DocumentAccountMappingRead"];
type TaxRateRead = components["schemas"]["TaxRateRead"];
type InvoiceRead = components["schemas"]["InvoiceRead"];
type CreditDebitNoteRead = components["schemas"]["CreditDebitNoteRead"];
type PaymentRead = components["schemas"]["PaymentRead"];
type CreditStatusRead = components["schemas"]["CreditStatusRead"];

type AccountCreate = z.infer<typeof schemas.AccountCreate>;
type DocumentAccountMappingCreate = z.infer<typeof schemas.DocumentAccountMappingCreate>;
type TaxRateCreate = z.infer<typeof schemas.TaxRateCreate>;
type InvoiceCreate = z.infer<typeof schemas.InvoiceCreate>;
type CreditDebitNoteCreate = z.infer<typeof schemas.CreditDebitNoteCreate>;
type PaymentCreate = z.infer<typeof schemas.PaymentCreate>;

// ---------------------------------------------------------------------------
// Plan de Cuentas
// ---------------------------------------------------------------------------

export function useAccounts() {
  return useQuery({
    queryKey: ["accounting", "accounts"],
    queryFn: () => apiRequest<AccountRead[]>("/accounting/accounts", { responseSchema: schemas.AccountRead.array() }),
  });
}

export function useCreateAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: AccountCreate) =>
      apiRequest<AccountRead>("/accounting/accounts", { method: "POST", body: payload, responseSchema: schemas.AccountRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounting", "accounts"] }),
  });
}

// ---------------------------------------------------------------------------
// Mapeo documento → cuentas
// ---------------------------------------------------------------------------

export function useDocumentAccountMappings() {
  return useQuery({
    queryKey: ["accounting", "document-account-mappings"],
    queryFn: () =>
      apiRequest<DocumentAccountMappingRead[]>("/accounting/document-account-mappings", {
        responseSchema: schemas.DocumentAccountMappingRead.array(),
      }),
  });
}

export function useUpsertDocumentAccountMapping() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: DocumentAccountMappingCreate) =>
      apiRequest<DocumentAccountMappingRead>("/accounting/document-account-mappings", {
        method: "POST",
        body: payload,
        responseSchema: schemas.DocumentAccountMappingRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounting", "document-account-mappings"] }),
  });
}

// ---------------------------------------------------------------------------
// Gestión de Impuestos
// ---------------------------------------------------------------------------

export function useTaxRates() {
  return useQuery({
    queryKey: ["accounting", "tax-rates"],
    queryFn: () => apiRequest<TaxRateRead[]>("/accounting/tax-rates", { responseSchema: schemas.TaxRateRead.array() }),
  });
}

export function useCreateTaxRate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TaxRateCreate) =>
      apiRequest<TaxRateRead>("/accounting/tax-rates", { method: "POST", body: payload, responseSchema: schemas.TaxRateRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounting", "tax-rates"] }),
  });
}

// ---------------------------------------------------------------------------
// Facturación de Venta y Proveedor
// ---------------------------------------------------------------------------

export function useInvoices() {
  return useQuery({
    queryKey: ["accounting", "invoices"],
    queryFn: () => apiRequest<InvoiceRead[]>("/accounting/invoices", { responseSchema: schemas.InvoiceRead.array() }),
  });
}

export function useInvoice(id: number | null) {
  return useQuery({
    queryKey: ["accounting", "invoices", id],
    queryFn: () => apiRequest<InvoiceRead>(`/accounting/invoices/${id}`, { responseSchema: schemas.InvoiceRead }),
    enabled: id !== null,
  });
}

export function useCreateInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: InvoiceCreate) =>
      apiRequest<InvoiceRead>("/accounting/invoices", { method: "POST", body: payload, responseSchema: schemas.InvoiceRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounting", "invoices"] }),
  });
}

function useInvoiceTransition(action: "post" | "cancel") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (invoiceId: number) =>
      apiRequest<InvoiceRead>(`/accounting/invoices/${invoiceId}/${action}`, { method: "POST", responseSchema: schemas.InvoiceRead }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounting", "invoices"] });
      qc.invalidateQueries({ queryKey: ["accounting", "credit-status"] });
    },
  });
}

export const usePostInvoice = () => useInvoiceTransition("post");
export const useCancelInvoice = () => useInvoiceTransition("cancel");

// ---------------------------------------------------------------------------
// Notas de Crédito y Débito
// ---------------------------------------------------------------------------

export function useCreditDebitNotes() {
  return useQuery({
    queryKey: ["accounting", "credit-debit-notes"],
    queryFn: () =>
      apiRequest<CreditDebitNoteRead[]>("/accounting/credit-debit-notes", { responseSchema: schemas.CreditDebitNoteRead.array() }),
  });
}

export function useCreditDebitNote(id: number | null) {
  return useQuery({
    queryKey: ["accounting", "credit-debit-notes", id],
    queryFn: () =>
      apiRequest<CreditDebitNoteRead>(`/accounting/credit-debit-notes/${id}`, { responseSchema: schemas.CreditDebitNoteRead }),
    enabled: id !== null,
  });
}

export function useCreateCreditDebitNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreditDebitNoteCreate) =>
      apiRequest<CreditDebitNoteRead>("/accounting/credit-debit-notes", {
        method: "POST",
        body: payload,
        responseSchema: schemas.CreditDebitNoteRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounting", "credit-debit-notes"] }),
  });
}

function useNoteTransition(action: "post" | "cancel") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (noteId: number) =>
      apiRequest<CreditDebitNoteRead>(`/accounting/credit-debit-notes/${noteId}/${action}`, {
        method: "POST",
        responseSchema: schemas.CreditDebitNoteRead,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounting", "credit-debit-notes"] });
      qc.invalidateQueries({ queryKey: ["accounting", "invoices"] });
    },
  });
}

export const usePostCreditDebitNote = () => useNoteTransition("post");
export const useCancelCreditDebitNote = () => useNoteTransition("cancel");

// ---------------------------------------------------------------------------
// Gestión de Pagos y Cobros
// ---------------------------------------------------------------------------

export function usePayments() {
  return useQuery({
    queryKey: ["accounting", "payments"],
    queryFn: () => apiRequest<PaymentRead[]>("/accounting/payments", { responseSchema: schemas.PaymentRead.array() }),
  });
}

export function usePayment(id: number | null) {
  return useQuery({
    queryKey: ["accounting", "payments", id],
    queryFn: () => apiRequest<PaymentRead>(`/accounting/payments/${id}`, { responseSchema: schemas.PaymentRead }),
    enabled: id !== null,
  });
}

export function useCreatePayment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: PaymentCreate) =>
      apiRequest<PaymentRead>("/accounting/payments", { method: "POST", body: payload, responseSchema: schemas.PaymentRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounting", "payments"] }),
  });
}

function usePaymentTransition(action: "post" | "cancel") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (paymentId: number) =>
      apiRequest<PaymentRead>(`/accounting/payments/${paymentId}/${action}`, { method: "POST", responseSchema: schemas.PaymentRead }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounting", "payments"] });
      qc.invalidateQueries({ queryKey: ["accounting", "invoices"] });
      qc.invalidateQueries({ queryKey: ["accounting", "credit-status"] });
    },
  });
}

export const usePostPayment = () => usePaymentTransition("post");
export const useCancelPayment = () => usePaymentTransition("cancel");

// ---------------------------------------------------------------------------
// Motor de Contención Financiera
// ---------------------------------------------------------------------------

export function useCreditStatus(contactId: number | null) {
  return useQuery({
    queryKey: ["accounting", "credit-status", contactId],
    queryFn: () =>
      apiRequest<CreditStatusRead>(`/accounting/credit-status/${contactId}`, { responseSchema: schemas.CreditStatusRead }),
    enabled: contactId !== null,
  });
}
