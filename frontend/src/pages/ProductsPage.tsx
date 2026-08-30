import { useState } from "react";
import { useMemo } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { schemas } from "@/lib/generated/schemas";
import { useProducts, useCreateProduct } from "@/hooks/use-inventory";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { ApiError } from "@/lib/api-client";
import { Plus } from "lucide-react";
import type { z } from "zod";
import type { components } from "@/lib/generated/api-types";

type ProductRead = components["schemas"]["ProductRead"];
type ProductCreateValues = z.input<typeof schemas.ProductCreate>;

const PRODUCT_TYPE_LABELS: Record<string, string> = {
  facturable: "Facturable",
  consumible: "Consumible",
  servicio: "Servicio",
};

function CreateProductDialog() {
  const [open, setOpen] = useState(false);
  const createProduct = useCreateProduct();
  const { register, handleSubmit, control, reset, formState: { errors, isSubmitting }, setError } = useForm<ProductCreateValues>({
    resolver: zodResolver(schemas.ProductCreate),
    defaultValues: { unit_of_measure: "unidad", tracks_lots: false },
  });

  const onSubmit = async (values: ProductCreateValues) => {
    try {
      const parsed = schemas.ProductCreate.parse(values);
      await createProduct.mutateAsync(parsed);
      reset();
      setOpen(false);
    } catch (err) {
      setError("root", { message: err instanceof ApiError ? err.message : "No se pudo crear el producto" });
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nuevo producto
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo producto</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sku">SKU</Label>
              <Input id="sku" {...register("sku")} />
              {errors.sku && <p className="text-sm text-destructive">{errors.sku.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="unit_of_measure">Unidad</Label>
              <Input id="unit_of_measure" {...register("unit_of_measure")} />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Nombre</Label>
            <Input id="name" {...register("name")} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Tipo</Label>
            <Controller
              control={control}
              name="product_type"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger>
                    <SelectValue placeholder="Elegir tipo…" />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(PRODUCT_TYPE_LABELS).map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.product_type && <p className="text-sm text-destructive">Elegí un tipo</p>}
          </div>

          <label className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" {...register("tracks_lots")} />
            Maneja lotes y vencimientos
          </label>

          {errors.root && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{errors.root.message}</p>}
          <Button type="submit" disabled={isSubmitting}>{isSubmitting ? "Creando…" : "Crear producto"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const columns: ColumnDef<ProductRead>[] = [
  { accessorKey: "sku", header: "SKU" },
  { accessorKey: "name", header: "Nombre" },
  { accessorKey: "product_type", header: "Tipo", cell: ({ getValue }) => PRODUCT_TYPE_LABELS[getValue<string>()] ?? getValue<string>() },
  { accessorKey: "unit_of_measure", header: "Unidad" },
  { accessorKey: "tracks_lots", header: "Lotes", cell: ({ getValue }) => (getValue<boolean>() ? "Sí" : "No") },
];

export function ProductsPage() {
  const { data, isLoading, error } = useProducts();
  const rows = useMemo(() => data ?? [], [data]);
  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Productos</h1>
          <p className="text-sm text-muted-foreground">Catálogo de productos y servicios.</p>
        </div>
        <CreateProductDialog />
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}
      {!isLoading && !error && rows.length === 0 && <p className="text-sm text-muted-foreground">Todavía no hay productos.</p>}

      {!isLoading && !error && rows.length > 0 && (
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((h) => <TableHead key={h.id}>{flexRender(h.column.columnDef.header, h.getContext())}</TableHead>)}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>)}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
