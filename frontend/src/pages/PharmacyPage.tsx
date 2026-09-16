import { useState } from "react";
import { useContacts } from "@/hooks/use-contacts";
import { useWarehouses, useProducts } from "@/hooks/use-inventory";
import {
  useDispensationsForPatient,
  useCreateDispensation,
  useVoidDispensation,
  useControlledSubstances,
  useMarkControlledSubstance,
  useUnmarkControlledSubstance,
  useControlledSubstanceLog,
  useMtmSessionsForPatient,
  useCreateMtmSession,
  useCancelMtmSession,
  useCloseMtmSession,
  useReorderPoints,
  useReorderSuggestions,
  useUpsertReorderPoint,
  useDeleteReorderPoint,
  useGeneratePurchaseOrderFromSuggestions,
  useProductActiveIngredients,
  useSetProductActiveIngredient,
  useCheckInteractions,
  useInsuranceProviders,
  useCreateInsuranceProvider,
  usePatientInsurancePolicies,
  useCreatePatientInsurancePolicy,
  useInsuranceClaims,
  useCreateInsuranceClaim,
  useSubmitInsuranceClaim,
  useApproveInsuranceClaim,
  useRejectInsuranceClaim,
  usePayInsuranceClaim,
} from "@/hooks/use-pharmacy";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { ApiError } from "@/lib/api-client";

interface LineFormState {
  productId: string;
  quantity: string;
}

const EMPTY_LINE: LineFormState = { productId: "", quantity: "" };

export function PharmacyPage() {
  return (
    <div className="flex flex-col gap-10">
      <header>
        <h1 className="font-display text-2xl font-medium text-foreground">Farmacia</h1>
        <p className="text-sm text-muted-foreground">Dispensación, verificación clínica y sustancias controladas.</p>
      </header>
      <DispensationSection />
      <MtmSection />
      <ReorderSection />
      <ControlledSubstancesSection />
      <InteractionsSection />
      <InsuranceSection />
    </div>
  );
}

function DispensationSection() {
  const { data: contacts } = useContacts("");
  const { data: warehouses } = useWarehouses();
  const { data: products } = useProducts();
  const createDispensation = useCreateDispensation();
  const voidDispensation = useVoidDispensation();

  const [patientId, setPatientId] = useState("");
  const { data: dispensations } = useDispensationsForPatient(patientId ? Number(patientId) : null);

  const [warehouseId, setWarehouseId] = useState("");
  const [lines, setLines] = useState<LineFormState[]>([{ ...EMPTY_LINE }]);
  const [mode, setMode] = useState<"prescription_free" | "walk_in">("prescription_free");
  const [walkInReference, setWalkInReference] = useState("");
  const [allergyNotes, setAllergyNotes] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("");
  const [amountCharged, setAmountCharged] = useState("");
  const [voidReasonByOrder, setVoidReasonByOrder] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [lastOrder, setLastOrder] = useState<{ document_number: string } | null>(null);

  const productName = (id: number) => products?.find((p) => p.id === id)?.name ?? `#${id}`;

  const updateLine = (index: number, patch: Partial<LineFormState>) => {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  };

  const submit = async () => {
    setError(null);
    setLastOrder(null);
    try {
      const order = await createDispensation.mutateAsync({
        warehouse_id: Number(warehouseId),
        patient_contact_id: Number(patientId),
        walk_in_reference: mode === "walk_in" ? walkInReference || "Venta de mostrador" : null,
        allergy_check_notes: allergyNotes || null,
        payment_method: paymentMethod || null,
        amount_charged: amountCharged || null,
        lines: lines
          .filter((l) => l.productId && l.quantity)
          .map((l) => ({ product_id: Number(l.productId), quantity: l.quantity })),
      });
      setLastOrder({ document_number: order.document_number });
      setLines([{ ...EMPTY_LINE }]);
      setAllergyNotes("");
      setWalkInReference("");
      setPaymentMethod("");
      setAmountCharged("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo registrar la dispensación");
    }
  };

  const submitVoid = async (orderId: number) => {
    const reason = voidReasonByOrder[orderId];
    if (!reason) return;
    try {
      await voidDispensation.mutateAsync({ orderId, payload: { void_reason: reason } });
      setVoidReasonByOrder((prev) => ({ ...prev, [orderId]: "" }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo anular la dispensación");
    }
  };

  const linesComplete = lines.some((l) => l.productId && l.quantity);

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-medium text-foreground">Dispensación / Venta de mostrador</h2>

      <div className="grid max-w-md grid-cols-2 gap-2">
        <Select value={patientId} onValueChange={setPatientId}>
          <SelectTrigger aria-label="Cliente"><SelectValue placeholder="Cliente" /></SelectTrigger>
          <SelectContent>
            {contacts?.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={warehouseId} onValueChange={setWarehouseId}>
          <SelectTrigger aria-label="Sucursal"><SelectValue placeholder="Sucursal" /></SelectTrigger>
          <SelectContent>
            {warehouses?.map((w) => <SelectItem key={w.id} value={String(w.id)}>{w.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {patientId && (
        <div className="flex flex-col gap-2">
          {(dispensations ?? []).map((d) => (
            <div key={d.id} className="flex flex-col gap-1 rounded-md border border-border p-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium text-foreground">{d.document_number}</span>
                {d.status === "voided" ? (
                  <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-medium text-destructive">Anulada</span>
                ) : (
                  <span className="text-xs text-muted-foreground">{new Date(d.dispensed_at).toLocaleString()}</span>
                )}
              </div>
              <ul className="flex flex-col gap-0.5">
                {d.lines.map((line) => (
                  <li key={line.id}>{productName(line.product_id)} — {line.quantity} {line.lot_id ? `(lote #${line.lot_id})` : ""}</li>
                ))}
              </ul>
              {d.status !== "voided" && (
                <div className="flex gap-2">
                  <Input
                    placeholder="Motivo de anulación"
                    value={voidReasonByOrder[d.id] ?? ""}
                    onChange={(e) => setVoidReasonByOrder((prev) => ({ ...prev, [d.id]: e.target.value }))}
                  />
                  <Button size="sm" variant="destructive" disabled={!voidReasonByOrder[d.id]} onClick={() => submitVoid(d.id)}>
                    Anular
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2 rounded-md border border-border p-3">
        <p className="text-xs font-medium text-muted-foreground">Nueva dispensación</p>

        <Select value={mode} onValueChange={(v) => setMode(v as "prescription_free" | "walk_in")}>
          <SelectTrigger aria-label="Tipo"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="prescription_free">Con receta externa (referencia libre)</SelectItem>
            <SelectItem value="walk_in">Venta de mostrador (POS, sin receta)</SelectItem>
          </SelectContent>
        </Select>
        {mode === "walk_in" && (
          <Input placeholder="Referencia (opcional)" value={walkInReference} onChange={(e) => setWalkInReference(e.target.value)} />
        )}

        {lines.map((line, i) => (
          <div key={i} className="flex gap-1">
            <Select value={line.productId} onValueChange={(v) => updateLine(i, { productId: v })}>
              <SelectTrigger aria-label="Medicamento"><SelectValue placeholder="Medicamento" /></SelectTrigger>
              <SelectContent>
                {products?.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Input placeholder="Cantidad" value={line.quantity} onChange={(e) => updateLine(i, { quantity: e.target.value })} />
            {lines.length > 1 && (
              <Button size="sm" variant="ghost" onClick={() => setLines((prev) => prev.filter((_, idx) => idx !== i))}>
                Quitar
              </Button>
            )}
          </div>
        ))}
        <Button size="sm" variant="ghost" className="w-fit" onClick={() => setLines((prev) => [...prev, { ...EMPTY_LINE }])}>
          + Agregar medicamento
        </Button>

        <Input
          placeholder="Alergias del cliente (obligatorio si no hay expediente médico)"
          value={allergyNotes}
          onChange={(e) => setAllergyNotes(e.target.value)}
        />
        <div className="grid grid-cols-2 gap-2">
          <Input placeholder="Método de pago (opcional)" value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)} />
          <Input placeholder="Monto cobrado (opcional)" value={amountCharged} onChange={(e) => setAmountCharged(e.target.value)} />
        </div>

        {error && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        {lastOrder && (
          <p className="rounded-md bg-emerald-100 px-3 py-2 text-sm text-emerald-800">
            Dispensación registrada: {lastOrder.document_number}
          </p>
        )}
        <Button size="sm" className="w-fit" disabled={!patientId || !warehouseId || !linesComplete} onClick={submit}>
          Dispensar
        </Button>
      </div>
    </section>
  );
}

function MtmSection() {
  const { data: contacts } = useContacts("");
  const createSession = useCreateMtmSession();
  const cancelSession = useCancelMtmSession();
  const closeSession = useCloseMtmSession();

  const [patientId, setPatientId] = useState("");
  const { data: sessions } = useMtmSessionsForPatient(patientId ? Number(patientId) : null);

  const [medicationReview, setMedicationReview] = useState("");
  const [adherenceNotes, setAdherenceNotes] = useState("");
  const [feeAmount, setFeeAmount] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    try {
      await createSession.mutateAsync({
        patient_contact_id: Number(patientId),
        session_date: new Date().toISOString().slice(0, 10),
        medication_review: medicationReview,
        adherence_notes: adherenceNotes || null,
        fee_amount: feeAmount,
      });
      setMedicationReview("");
      setAdherenceNotes("");
      setFeeAmount("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo registrar la sesión de MTM");
    }
  };

  const closeWithReceipt = async (sessionId: number) => {
    try {
      await closeSession.mutateAsync({ sessionId, payload: { issue_date: new Date().toISOString().slice(0, 10) } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo cerrar la sesión");
    }
  };

  const cancel = async (sessionId: number) => {
    const reason = window.prompt("Motivo de la cancelación:");
    if (!reason) return;
    try {
      await cancelSession.mutateAsync({ sessionId, payload: { cancel_reason: reason } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo cancelar la sesión");
    }
  };

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-medium text-foreground">MTM / Consulta Farmacéutica</h2>
      <p className="text-sm text-muted-foreground">
        Sesión de asesoría (revisión de medicación, adherencia) facturable independiente de una dispensación puntual.
      </p>

      <div className="grid max-w-md grid-cols-1 gap-2">
        <Select value={patientId} onValueChange={setPatientId}>
          <SelectTrigger aria-label="Paciente"><SelectValue placeholder="Paciente" /></SelectTrigger>
          <SelectContent>
            {contacts?.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {patientId && (
        <div className="flex flex-col gap-2">
          {(sessions ?? []).map((s) => (
            <div key={s.id} className="flex flex-col gap-1 rounded-md border border-border p-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium text-foreground">{s.session_date} — {s.fee_amount} {s.currency_code}</span>
                <span
                  className={
                    s.status === "closed"
                      ? "rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary"
                      : s.status === "cancelled"
                        ? "rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-medium text-destructive"
                        : "rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
                  }
                >
                  {s.status === "closed" ? "Cerrada" : s.status === "cancelled" ? "Cancelada" : "Abierta"}
                </span>
              </div>
              <p className="text-muted-foreground">{s.medication_review}</p>
              {s.status === "open" && (
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => closeWithReceipt(s.id)} disabled={closeSession.isPending}>
                    Cerrar y facturar
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => cancel(s.id)} disabled={cancelSession.isPending}>
                    Cancelar
                  </Button>
                </div>
              )}
            </div>
          ))}
          {(sessions ?? []).length === 0 && <p className="text-sm text-muted-foreground">Sin sesiones de MTM para este paciente.</p>}
        </div>
      )}

      <div className="flex max-w-md flex-col gap-2">
        <textarea
          placeholder="Revisión de medicación (obligatorio)"
          className="flex min-h-20 w-full rounded-md border border-input bg-card px-3 py-2 text-sm placeholder:text-muted-foreground"
          value={medicationReview}
          onChange={(e) => setMedicationReview(e.target.value)}
        />
        <textarea
          placeholder="Notas de adherencia (opcional)"
          className="flex min-h-16 w-full rounded-md border border-input bg-card px-3 py-2 text-sm placeholder:text-muted-foreground"
          value={adherenceNotes}
          onChange={(e) => setAdherenceNotes(e.target.value)}
        />
        <Input placeholder="Monto de la sesión" value={feeAmount} onChange={(e) => setFeeAmount(e.target.value)} />
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <Button
          size="sm" className="w-fit"
          disabled={!patientId || !medicationReview || !feeAmount}
          onClick={submit}
        >
          Registrar sesión
        </Button>
      </div>
    </section>
  );
}

function ReorderSection() {
  const { data: warehouses } = useWarehouses();
  const { data: products } = useProducts();
  const { data: contacts } = useContacts("");
  const vendors = (contacts ?? []).filter((c) => (c as { is_vendor?: boolean }).is_vendor);

  const [warehouseId, setWarehouseId] = useState("");
  const wId = warehouseId ? Number(warehouseId) : null;
  const { data: suggestions } = useReorderSuggestions(wId);
  const { data: points } = useReorderPoints(wId);
  const upsertPoint = useUpsertReorderPoint();
  const deletePoint = useDeleteReorderPoint();
  const generatePo = useGeneratePurchaseOrderFromSuggestions();

  const [configProductId, setConfigProductId] = useState("");
  const [reorderPoint, setReorderPoint] = useState("");
  const [reorderQuantity, setReorderQuantity] = useState("");
  const [vendorByProduct, setVendorByProduct] = useState<Record<number, string>>({});
  const [costByProduct, setCostByProduct] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);

  const productName = (id: number) => products?.find((p) => p.id === id)?.name ?? `#${id}`;

  const saveReorderPoint = async () => {
    if (!wId || !configProductId || !reorderPoint || !reorderQuantity) return;
    try {
      await upsertPoint.mutateAsync({
        product_id: Number(configProductId), warehouse_id: wId,
        reorder_point: reorderPoint, reorder_quantity: reorderQuantity,
      });
      setConfigProductId(""); setReorderPoint(""); setReorderQuantity("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo guardar el punto de pedido");
    }
  };

  const generateForProduct = async (productId: number, quantity: string) => {
    const vendorId = vendorByProduct[productId];
    const unitCost = costByProduct[productId];
    if (!wId || !vendorId || !unitCost) {
      setError("Elegí proveedor y costo unitario antes de generar la orden de compra");
      return;
    }
    try {
      await generatePo.mutateAsync({
        warehouse_id: wId, vendor_id: Number(vendorId),
        lines: [{ product_id: productId, quantity, unit_cost: unitCost }],
      });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.code === "PACKAGE_NOT_LICENSED"
            ? "Generar la orden de compra requiere el paquete Administrativo completo — mientras tanto, esta lista sirve para exportar manualmente."
            : err.message
          : "No se pudo generar la orden de compra"
      );
    }
  };

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-medium text-foreground">Reposición a Droguerías</h2>
      <p className="text-sm text-muted-foreground">
        Sugerencia de reorden por punto de pedido. Generar la orden de compra requiere el paquete Administrativo
        completo — sin él, esta lista queda como referencia exportable.
      </p>

      <Select value={warehouseId} onValueChange={setWarehouseId}>
        <SelectTrigger aria-label="Sucursal" className="w-64"><SelectValue placeholder="Sucursal" /></SelectTrigger>
        <SelectContent>
          {warehouses?.map((w) => <SelectItem key={w.id} value={String(w.id)}>{w.name}</SelectItem>)}
        </SelectContent>
      </Select>

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

      {wId && (
        <>
          <div className="flex flex-col gap-2">
            {(suggestions ?? []).map((s) => (
              <div key={s.product_id} className="flex flex-wrap items-center gap-2 rounded-md border border-border p-2 text-sm">
                <span className="min-w-40 font-medium text-foreground">{productName(s.product_id)}</span>
                <span className="text-muted-foreground">
                  Disponible: {s.available_quantity} · Punto: {s.reorder_point} · Sugerido: {s.reorder_quantity}
                </span>
                <Select value={vendorByProduct[s.product_id] ?? ""} onValueChange={(v) => setVendorByProduct((p) => ({ ...p, [s.product_id]: v }))}>
                  <SelectTrigger aria-label="Proveedor" className="w-40"><SelectValue placeholder="Proveedor" /></SelectTrigger>
                  <SelectContent>
                    {vendors.map((v) => <SelectItem key={v.id} value={String(v.id)}>{v.name}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Input
                  placeholder="Costo unitario" className="w-32"
                  value={costByProduct[s.product_id] ?? ""}
                  onChange={(e) => setCostByProduct((p) => ({ ...p, [s.product_id]: e.target.value }))}
                />
                <Button size="sm" variant="outline" disabled={generatePo.isPending} onClick={() => generateForProduct(s.product_id, String(s.reorder_quantity))}>
                  Generar PO
                </Button>
              </div>
            ))}
            {(suggestions ?? []).length === 0 && <p className="text-sm text-muted-foreground">Sin sugerencias de reposición para esta sucursal.</p>}
          </div>

          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-medium text-foreground">Puntos de pedido configurados</h3>
            {(points ?? []).map((p) => (
              <div key={p.id} className="flex items-center justify-between rounded-md border border-border p-2 text-sm">
                <span>{productName(p.product_id)} — punto {p.reorder_point}, reponer {p.reorder_quantity}</span>
                <Button size="sm" variant="ghost" onClick={() => deletePoint.mutate(p.id)}>Quitar</Button>
              </div>
            ))}
          </div>

          <div className="flex max-w-lg flex-wrap items-end gap-2">
            <Select value={configProductId} onValueChange={setConfigProductId}>
              <SelectTrigger aria-label="Producto" className="w-48"><SelectValue placeholder="Producto" /></SelectTrigger>
              <SelectContent>
                {products?.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Input placeholder="Punto de pedido" className="w-32" value={reorderPoint} onChange={(e) => setReorderPoint(e.target.value)} />
            <Input placeholder="Cantidad a reponer" className="w-36" value={reorderQuantity} onChange={(e) => setReorderQuantity(e.target.value)} />
            <Button size="sm" disabled={!configProductId || !reorderPoint || !reorderQuantity} onClick={saveReorderPoint}>
              Guardar punto de pedido
            </Button>
          </div>
        </>
      )}
    </section>
  );
}

function ControlledSubstancesSection() {
  const { data: products } = useProducts();
  const { data: controlled } = useControlledSubstances();
  const { data: log } = useControlledSubstanceLog();
  const markControlled = useMarkControlledSubstance();
  const unmarkControlled = useUnmarkControlledSubstance();

  const [productId, setProductId] = useState("");
  const [showLog, setShowLog] = useState(false);

  const productName = (id: number) => products?.find((p) => p.id === id)?.name ?? `#${id}`;
  const isControlled = (id: number) => (controlled ?? []).some((c) => c.product_id === id);

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-medium text-foreground">Sustancias Controladas</h2>

      <div className="flex gap-2">
        <Select value={productId} onValueChange={setProductId}>
          <SelectTrigger aria-label="Producto a marcar" className="max-w-xs"><SelectValue placeholder="Producto" /></SelectTrigger>
          <SelectContent>
            {products?.filter((p) => !isControlled(p.id)).map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Button size="sm" disabled={!productId} onClick={() => { markControlled.mutate(Number(productId)); setProductId(""); }}>
          Marcar como controlado
        </Button>
      </div>

      <div className="flex flex-col divide-y divide-border rounded-md border border-border">
        {(controlled ?? []).map((c) => (
          <div key={c.id} className="flex items-center justify-between px-4 py-2 text-sm">
            <span>{productName(c.product_id)}</span>
            <Button size="sm" variant="ghost" onClick={() => unmarkControlled.mutate(c.product_id)}>
              Quitar marca
            </Button>
          </div>
        ))}
        {(controlled ?? []).length === 0 && <p className="px-4 py-3 text-sm text-muted-foreground">Sin productos marcados.</p>}
      </div>

      <Button size="sm" variant="outline" className="w-fit" onClick={() => setShowLog((v) => !v)}>
        {showLog ? "Ocultar libro de registro" : "Ver libro de registro"}
      </Button>
      {showLog && (
        <div className="flex flex-col divide-y divide-border rounded-md border border-border">
          {(log ?? []).map((entry) => (
            <div key={entry.id} className="flex items-center justify-between px-4 py-2 text-sm">
              <span>{productName(entry.product_id)} — {entry.quantity}</span>
              <span className="text-xs text-muted-foreground">{new Date(entry.created_at).toLocaleString()}</span>
            </div>
          ))}
          {(log ?? []).length === 0 && <p className="px-4 py-3 text-sm text-muted-foreground">Sin movimientos registrados.</p>}
        </div>
      )}
    </section>
  );
}

function InteractionsSection() {
  const { data: products } = useProducts();
  const { data: ingredients } = useProductActiveIngredients();
  const setIngredient = useSetProductActiveIngredient();
  const checkInteractions = useCheckInteractions();

  const [mapProductId, setMapProductId] = useState("");
  const [ingredientText, setIngredientText] = useState("");
  const [checkProductIds, setCheckProductIds] = useState<string[]>(["", ""]);
  const [error, setError] = useState<string | null>(null);

  const productName = (id: number) => products?.find((p) => p.id === id)?.name ?? `#${id}`;
  const ingredientFor = (id: number) => ingredients?.find((i) => i.product_id === id)?.active_ingredient;

  const saveIngredient = async () => {
    if (!mapProductId || !ingredientText) return;
    try {
      await setIngredient.mutateAsync({ product_id: Number(mapProductId), active_ingredient: ingredientText });
      setMapProductId("");
      setIngredientText("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo guardar el principio activo");
    }
  };

  const updateCheckProduct = (index: number, value: string) => {
    setCheckProductIds((prev) => prev.map((v, i) => (i === index ? value : v)));
  };

  const runCheck = async () => {
    setError(null);
    checkInteractions.reset();
    const ids = checkProductIds.filter(Boolean).map(Number);
    if (ids.length < 2) return;
    try {
      await checkInteractions.mutateAsync({ product_ids: ids });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo chequear interacciones");
    }
  };

  const result = checkInteractions.data;

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-medium text-foreground">Interacciones</h2>
      <p className="text-sm text-muted-foreground">
        Chequeo de interacciones medicamento-medicamento contra un catálogo de referencia
        (ambiente de desarrollo — ver nota en STATE.md sobre integración con API externa real).
      </p>

      <div className="flex flex-col gap-2 rounded-md border border-border p-3">
        <p className="text-xs font-medium text-muted-foreground">Mapear principio activo de un producto</p>
        <div className="flex gap-2">
          <Select value={mapProductId} onValueChange={setMapProductId}>
            <SelectTrigger aria-label="Producto a mapear" className="max-w-xs"><SelectValue placeholder="Producto" /></SelectTrigger>
            <SelectContent>
              {products?.map((p) => (
                <SelectItem key={p.id} value={String(p.id)}>
                  {p.name}{ingredientFor(p.id) ? ` (${ingredientFor(p.id)})` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input placeholder="Principio activo" value={ingredientText} onChange={(e) => setIngredientText(e.target.value)} />
          <Button size="sm" disabled={!mapProductId || !ingredientText} onClick={saveIngredient}>
            Guardar
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-2 rounded-md border border-border p-3">
        <p className="text-xs font-medium text-muted-foreground">Chequear interacciones entre productos</p>
        <div className="flex flex-wrap gap-2">
          {checkProductIds.map((value, i) => (
            <Select key={i} value={value} onValueChange={(v) => updateCheckProduct(i, v)}>
              <SelectTrigger aria-label={`Producto ${i + 1}`} className="max-w-xs"><SelectValue placeholder="Producto" /></SelectTrigger>
              <SelectContent>
                {products?.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
              </SelectContent>
            </Select>
          ))}
          <Button size="sm" variant="ghost" onClick={() => setCheckProductIds((prev) => [...prev, ""])}>
            + Agregar producto
          </Button>
        </div>
        <Button size="sm" className="w-fit" disabled={checkProductIds.filter(Boolean).length < 2} onClick={runCheck}>
          Chequear
        </Button>

        {error && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}

        {result && (
          <div className="flex flex-col gap-2">
            {result.warnings.length === 0 ? (
              <p className="rounded-md bg-emerald-100 px-3 py-2 text-sm text-emerald-800">Sin interacciones conocidas.</p>
            ) : (
              result.warnings.map((w, i) => (
                <div
                  key={i}
                  role="alert"
                  className={`rounded-md px-3 py-2 text-sm ${w.severity === "major" ? "bg-destructive/10 text-destructive" : "bg-amber-100 text-amber-800"}`}
                >
                  <p className="font-medium">
                    {productName(w.product_id_a)} + {productName(w.product_id_b)} — {w.severity === "major" ? "Severidad alta" : "Severidad moderada"}
                  </p>
                  <p>{w.description}</p>
                </div>
              ))
            )}
            {result.unchecked_product_ids.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Sin principio activo mapeado (no incluidos en el chequeo): {result.unchecked_product_ids.map(productName).join(", ")}
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function InsuranceSection() {
  const { data: contacts } = useContacts("");
  const { data: providers } = useInsuranceProviders();
  const createProvider = useCreateInsuranceProvider();
  const createPolicy = useCreatePatientInsurancePolicy();
  const { data: claims } = useInsuranceClaims();
  const createClaim = useCreateInsuranceClaim();
  const submitClaim = useSubmitInsuranceClaim();
  const approveClaim = useApproveInsuranceClaim();
  const rejectClaim = useRejectInsuranceClaim();
  const payClaim = usePayInsuranceClaim();

  const [error, setError] = useState<string | null>(null);

  // Aseguradoras
  const [newProviderContactId, setNewProviderContactId] = useState("");
  const [newProviderCoverage, setNewProviderCoverage] = useState("");

  // Pólizas
  const [policyPatientId, setPolicyPatientId] = useState("");
  const [policyProviderId, setPolicyProviderId] = useState("");
  const [policyNumber, setPolicyNumber] = useState("");
  const [policyCoverage, setPolicyCoverage] = useState("");
  const { data: policies } = usePatientInsurancePolicies(policyPatientId ? Number(policyPatientId) : null);

  // Reclamos
  const [claimPatientId, setClaimPatientId] = useState("");
  const { data: patientDispensations } = useDispensationsForPatient(claimPatientId ? Number(claimPatientId) : null);
  const [claimOrderId, setClaimOrderId] = useState("");
  const [claimProviderId, setClaimProviderId] = useState("");
  const [claimTotal, setClaimTotal] = useState("");
  const [claimCopay, setClaimCopay] = useState("");
  const [rejectionByClaimId, setRejectionByClaimId] = useState<Record<number, string>>({});

  const customerContacts = contacts?.filter((c) => c.is_customer) ?? [];
  const claimedAmount = (() => {
    const total = Number(claimTotal);
    const copay = Number(claimCopay);
    if (!claimTotal || !claimCopay || Number.isNaN(total) || Number.isNaN(copay)) return "";
    return (total - copay).toFixed(2);
  })();

  const providerContactName = (providerId: number) => {
    const provider = providers?.find((p) => p.id === providerId);
    return contacts?.find((c) => c.id === provider?.contact_id)?.name ?? `#${providerId}`;
  };

  const submitNewProvider = async () => {
    if (!newProviderContactId) return;
    try {
      await createProvider.mutateAsync({
        contact_id: Number(newProviderContactId),
        default_coverage_percentage: newProviderCoverage || null,
      });
      setNewProviderContactId("");
      setNewProviderCoverage("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo crear la aseguradora");
    }
  };

  const submitNewPolicy = async () => {
    if (!policyPatientId || !policyProviderId || !policyNumber || !policyCoverage) return;
    try {
      await createPolicy.mutateAsync({
        patient_contact_id: Number(policyPatientId), insurance_provider_id: Number(policyProviderId),
        policy_number: policyNumber, coverage_percentage: policyCoverage,
      });
      setPolicyNumber("");
      setPolicyCoverage("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo crear la póliza");
    }
  };

  const submitNewClaim = async () => {
    if (!claimOrderId || !claimProviderId || !claimTotal || !claimCopay || !claimedAmount) return;
    try {
      await createClaim.mutateAsync({
        dispensation_order_id: Number(claimOrderId), insurance_provider_id: Number(claimProviderId),
        amount_total: claimTotal, amount_patient_copay: claimCopay, amount_claimed_insurer: claimedAmount,
      });
      setClaimTotal("");
      setClaimCopay("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo crear el reclamo");
    }
  };

  const claimAction = async (fn: () => Promise<unknown>, message: string) => {
    try {
      await fn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : message);
    }
  };

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-medium text-foreground">Aseguradoras y Reclamos</h2>
      <p className="text-sm text-muted-foreground">
        Copagos y reclamos a aseguradoras, conciliados contra el motor real de facturación cuando
        el paquete Administrativo está activo (ver STATE.md, módulo 18).
      </p>

      {error && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}

      <div className="flex flex-col gap-2 rounded-md border border-border p-3">
        <p className="text-xs font-medium text-muted-foreground">Nueva aseguradora (contacto con rol cliente)</p>
        <div className="flex gap-2">
          <Select value={newProviderContactId} onValueChange={setNewProviderContactId}>
            <SelectTrigger aria-label="Contacto aseguradora" className="max-w-xs"><SelectValue placeholder="Contacto" /></SelectTrigger>
            <SelectContent>
              {customerContacts.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <Input placeholder="% cobertura por defecto" value={newProviderCoverage} onChange={(e) => setNewProviderCoverage(e.target.value)} className="max-w-40" />
          <Button size="sm" disabled={!newProviderContactId} onClick={submitNewProvider}>Crear aseguradora</Button>
        </div>
        <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
          {providers?.map((p) => (
            <li key={p.id}>{providerContactName(p.id)}{p.default_coverage_percentage ? ` — ${p.default_coverage_percentage}% por defecto` : ""}</li>
          ))}
        </ul>
      </div>

      <div className="flex flex-col gap-2 rounded-md border border-border p-3">
        <p className="text-xs font-medium text-muted-foreground">Pólizas de paciente</p>
        <div className="flex flex-wrap gap-2">
          <Select value={policyPatientId} onValueChange={setPolicyPatientId}>
            <SelectTrigger aria-label="Paciente póliza" className="max-w-xs"><SelectValue placeholder="Paciente" /></SelectTrigger>
            <SelectContent>{contacts?.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={policyProviderId} onValueChange={setPolicyProviderId}>
            <SelectTrigger aria-label="Aseguradora póliza" className="max-w-xs"><SelectValue placeholder="Aseguradora" /></SelectTrigger>
            <SelectContent>{providers?.map((p) => <SelectItem key={p.id} value={String(p.id)}>{providerContactName(p.id)}</SelectItem>)}</SelectContent>
          </Select>
          <Input placeholder="No. de póliza" value={policyNumber} onChange={(e) => setPolicyNumber(e.target.value)} className="max-w-40" />
          <Input placeholder="% cobertura" value={policyCoverage} onChange={(e) => setPolicyCoverage(e.target.value)} className="max-w-32" />
          <Button size="sm" disabled={!policyPatientId || !policyProviderId || !policyNumber || !policyCoverage} onClick={submitNewPolicy}>
            Guardar póliza
          </Button>
        </div>
        {policyPatientId && (
          <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
            {policies?.map((p) => (
              <li key={p.id}>{providerContactName(p.insurance_provider_id)} — {p.policy_number} ({p.coverage_percentage}%)</li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-col gap-2 rounded-md border border-border p-3">
        <p className="text-xs font-medium text-muted-foreground">Nuevo reclamo</p>
        <div className="flex flex-wrap gap-2">
          <Select value={claimPatientId} onValueChange={(v) => { setClaimPatientId(v); setClaimOrderId(""); }}>
            <SelectTrigger aria-label="Paciente reclamo" className="max-w-xs"><SelectValue placeholder="Paciente" /></SelectTrigger>
            <SelectContent>{contacts?.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={claimOrderId} onValueChange={setClaimOrderId}>
            <SelectTrigger aria-label="Dispensación reclamo" className="max-w-xs"><SelectValue placeholder="Dispensación" /></SelectTrigger>
            <SelectContent>
              {patientDispensations?.map((d) => <SelectItem key={d.id} value={String(d.id)}>{d.document_number}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={claimProviderId} onValueChange={setClaimProviderId}>
            <SelectTrigger aria-label="Aseguradora reclamo" className="max-w-xs"><SelectValue placeholder="Aseguradora" /></SelectTrigger>
            <SelectContent>{providers?.map((p) => <SelectItem key={p.id} value={String(p.id)}>{providerContactName(p.id)}</SelectItem>)}</SelectContent>
          </Select>
          <Input placeholder="Monto total" value={claimTotal} onChange={(e) => setClaimTotal(e.target.value)} className="max-w-28" />
          <Input placeholder="Copago paciente" value={claimCopay} onChange={(e) => setClaimCopay(e.target.value)} className="max-w-32" />
          <span className="self-center text-xs text-muted-foreground">Reclamado a aseguradora: {claimedAmount || "—"}</span>
          <Button size="sm" disabled={!claimOrderId || !claimProviderId || !claimTotal || !claimCopay} onClick={submitNewClaim}>
            Crear reclamo
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-2 rounded-md border border-border p-3">
        <p className="text-xs font-medium text-muted-foreground">Reclamos</p>
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr><th className="py-1.5">No.</th><th className="py-1.5">Estado</th><th className="py-1.5">Copago</th><th className="py-1.5">Reclamado</th><th className="py-1.5">Acciones</th></tr>
          </thead>
          <tbody>
            {claims?.map((c) => (
              <tr key={c.id} className="border-t border-border">
                <td className="py-1.5">{c.claim_number}</td>
                <td className="py-1.5">{c.status}</td>
                <td className="py-1.5">{c.amount_patient_copay}</td>
                <td className="py-1.5">{c.amount_claimed_insurer}</td>
                <td className="py-1.5">
                  <div className="flex flex-wrap items-center gap-1">
                    {c.status === "pending" && (
                      <Button size="sm" variant="ghost" onClick={() => claimAction(() => submitClaim.mutateAsync(c.id), "No se pudo enviar")}>Enviar</Button>
                    )}
                    {c.status === "submitted" && (
                      <Button size="sm" variant="ghost" onClick={() => claimAction(() => approveClaim.mutateAsync(c.id), "No se pudo aprobar")}>Aprobar</Button>
                    )}
                    {(c.status === "pending" || c.status === "submitted") && (
                      <>
                        <Input
                          placeholder="Motivo de rechazo" className="h-8 max-w-40 text-xs"
                          value={rejectionByClaimId[c.id] ?? ""}
                          onChange={(e) => setRejectionByClaimId((prev) => ({ ...prev, [c.id]: e.target.value }))}
                        />
                        <Button
                          size="sm" variant="ghost"
                          disabled={!rejectionByClaimId[c.id]}
                          onClick={() => claimAction(
                            () => rejectClaim.mutateAsync({ claimId: c.id, payload: { rejection_reason: rejectionByClaimId[c.id] } }),
                            "No se pudo rechazar",
                          )}
                        >
                          Rechazar
                        </Button>
                      </>
                    )}
                    {c.status === "approved" && (
                      <Button size="sm" variant="ghost" onClick={() => claimAction(() => payClaim.mutateAsync({ claimId: c.id, payload: {} }), "No se pudo liquidar")}>
                        Marcar pagado
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
