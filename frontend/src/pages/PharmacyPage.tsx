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
  useProductActiveIngredients,
  useSetProductActiveIngredient,
  useCheckInteractions,
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
      <ControlledSubstancesSection />
      <InteractionsSection />
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
