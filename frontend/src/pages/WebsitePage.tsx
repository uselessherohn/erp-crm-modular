import { useState } from "react";
import {
  useWebsitePages,
  useCreateWebsitePage,
  useUpdateWebsitePage,
  usePublishWebsitePage,
  useUnpublishWebsitePage,
  useWebsiteFormSubmissions,
} from "@/hooks/use-website";
import { WebsitePageCreate, type WebsitePageRead } from "@/lib/website-temp-contract";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";

const TEXTAREA_CLASS =
  "flex w-full rounded-md border border-input bg-card px-3 py-2 text-sm placeholder:text-muted-foreground";

export function WebsitePage() {
  return (
    <div className="flex flex-col gap-10">
      <header>
        <h1 className="font-display text-2xl font-medium text-foreground">Sitio Web</h1>
        <p className="text-sm text-muted-foreground">
          Páginas del CMS y formularios de captación recibidos.
        </p>
      </header>
      <PagesSection />
      <FormSubmissionsSection />
    </div>
  );
}

function PagesSection() {
  const { data: pages, isLoading, error } = useWebsitePages();
  const createPage = useCreateWebsitePage();
  const updatePage = useUpdateWebsitePage();
  const publishPage = usePublishWebsitePage();
  const unpublishPage = useUnpublishWebsitePage();

  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState({ slug: "", title: "", content: "" });
  const [formError, setFormError] = useState<string | null>(null);

  const startCreate = () => {
    setEditingId(null);
    setForm({ slug: "", title: "", content: "" });
    setFormError(null);
  };

  const startEdit = (page: WebsitePageRead) => {
    setEditingId(page.id);
    setForm({ slug: page.slug, title: page.title, content: page.content });
    setFormError(null);
  };

  const submit = async () => {
    setFormError(null);
    try {
      if (editingId) {
        await updatePage.mutateAsync({ pageId: editingId, payload: { title: form.title, content: form.content } });
      } else {
        const parsed = WebsitePageCreate.parse(form);
        await createPage.mutateAsync(parsed);
      }
      startCreate();
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.message);
      } else if (err instanceof Error) {
        setFormError(err.message);
      } else {
        setFormError("No se pudo guardar la página");
      }
    }
  };

  const togglePublish = async (page: WebsitePageRead) => {
    if (page.status === "published") {
      await unpublishPage.mutateAsync(page.id);
    } else {
      await publishPage.mutateAsync(page.id);
    }
  };

  return (
    <section className="flex flex-col gap-4">
      <h2 className="font-display text-lg font-medium text-foreground">Páginas</h2>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error instanceof ApiError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error.code === "PERMISSION_DENIED" ? "No tenés permiso para ver las páginas del sitio." : error.message}
        </p>
      )}

      {!isLoading && !error && (
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Título</th>
                <th className="px-3 py-2">Slug</th>
                <th className="px-3 py-2">Estado</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {(pages ?? []).map((page) => (
                <tr key={page.id} className="border-t border-border">
                  <td className="cursor-pointer px-3 py-2" onClick={() => startEdit(page)}>
                    {page.title}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">/{page.slug}</td>
                  <td className="px-3 py-2">
                    <span
                      className={
                        page.status === "published"
                          ? "rounded bg-secondary px-2 py-0.5 text-xs text-secondary-foreground"
                          : "rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                      }
                    >
                      {page.status === "published" ? "Publicada" : "Borrador"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button variant="ghost" size="sm" onClick={() => togglePublish(page)}>
                      {page.status === "published" ? "Despublicar" : "Publicar"}
                    </Button>
                  </td>
                </tr>
              ))}
              {(pages ?? []).length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-4 text-center text-muted-foreground">
                    Todavía no hay páginas.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-col gap-3 rounded-md border border-border p-4">
        <h3 className="text-sm font-medium text-foreground">{editingId ? "Editar página" : "Nueva página"}</h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="page-slug">Slug</Label>
            <Input
              id="page-slug"
              placeholder="quienes-somos"
              value={form.slug}
              disabled={editingId !== null}
              onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="page-title">Título</Label>
            <Input
              id="page-title"
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="page-content">Contenido</Label>
          <textarea
            id="page-content"
            className={TEXTAREA_CLASS}
            rows={4}
            value={form.content}
            onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
          />
        </div>

        {formError && (
          <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {formError}
          </p>
        )}

        <div className="flex gap-2">
          <Button size="sm" onClick={submit} disabled={createPage.isPending || updatePage.isPending}>
            {editingId ? "Guardar cambios" : "Crear página"}
          </Button>
          {editingId && (
            <Button size="sm" variant="ghost" onClick={startCreate}>
              Cancelar
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}

function FormSubmissionsSection() {
  const { data: submissions, isLoading, error } = useWebsiteFormSubmissions();

  return (
    <section className="flex flex-col gap-4">
      <h2 className="font-display text-lg font-medium text-foreground">Formularios recibidos</h2>
      <p className="text-sm text-muted-foreground">
        Cada envío crea o actualiza un contacto marcado como prospecto en Contactos.
      </p>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error instanceof ApiError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error.code === "PERMISSION_DENIED" ? "No tenés permiso para ver los envíos." : error.message}
        </p>
      )}

      {!isLoading && !error && (
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Formulario</th>
                <th className="px-3 py-2">Nombre</th>
                <th className="px-3 py-2">Correo</th>
                <th className="px-3 py-2">Mensaje</th>
              </tr>
            </thead>
            <tbody>
              {(submissions ?? []).map((s) => (
                <tr key={s.id} className="border-t border-border">
                  <td className="px-3 py-2">{s.form_name}</td>
                  <td className="px-3 py-2">{typeof s.payload.name === "string" ? s.payload.name : "—"}</td>
                  <td className="px-3 py-2">{typeof s.payload.email === "string" ? s.payload.email : "—"}</td>
                  <td className="max-w-xs truncate px-3 py-2 text-muted-foreground">
                    {typeof s.payload.message === "string" ? s.payload.message : "—"}
                  </td>
                </tr>
              ))}
              {(submissions ?? []).length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-4 text-center text-muted-foreground">
                    Todavía no hay envíos.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
