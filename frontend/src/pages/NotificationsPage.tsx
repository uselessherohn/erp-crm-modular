import { useState } from "react";
import { useUsers } from "@/hooks/use-core-data";
import {
  useNotificationTemplates,
  useCreateNotificationTemplate,
  useUpdateNotificationTemplate,
  useSendNotification,
} from "@/hooks/use-notification-templates";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { ApiError } from "@/lib/api-client";

const TEXTAREA_CLASS = "flex w-full rounded-md border border-input bg-card px-3 py-2 text-sm placeholder:text-muted-foreground";

export function NotificationsPage() {
  return (
    <div className="flex flex-col gap-10">
      <header>
        <h1 className="font-display text-2xl font-medium text-foreground">Notificaciones</h1>
        <p className="text-sm text-muted-foreground">Plantillas dinámicas y envío manual.</p>
      </header>
      <TemplatesSection />
      <SendSection />
    </div>
  );
}

function TemplatesSection() {
  const { data: templates, isLoading, error } = useNotificationTemplates();
  const createTemplate = useCreateNotificationTemplate();
  const updateTemplate = useUpdateNotificationTemplate();

  const [editingCode, setEditingCode] = useState<string | null>(null);
  const [form, setForm] = useState({ code: "", subject_template: "", body_template: "" });
  const [formError, setFormError] = useState<string | null>(null);

  const startCreate = () => {
    setEditingCode(null);
    setForm({ code: "", subject_template: "", body_template: "" });
  };

  const startEdit = (t: { code: string; subject_template: string; body_template: string }) => {
    setEditingCode(t.code);
    setForm({ code: t.code, subject_template: t.subject_template, body_template: t.body_template });
  };

  const submit = async () => {
    setFormError(null);
    try {
      if (editingCode) {
        await updateTemplate.mutateAsync({
          code: editingCode,
          payload: { subject_template: form.subject_template, body_template: form.body_template },
        });
      } else {
        await createTemplate.mutateAsync(form);
      }
      startCreate();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "No se pudo guardar la plantilla");
    }
  };

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-medium text-foreground">Plantillas</h2>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando plantillas…</p>}
      {error instanceof ApiError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>
      )}
      {!isLoading && (templates ?? []).length === 0 && <p className="text-sm text-muted-foreground">Sin plantillas todavía.</p>}

      <div className="flex flex-col divide-y divide-border rounded-md border border-border">
        {(templates ?? []).map((t) => (
          <button
            key={t.id}
            onClick={() => startEdit(t)}
            className="flex flex-col gap-0.5 px-4 py-3 text-left text-sm hover:bg-muted"
          >
            <span className="font-medium text-foreground">{t.code}</span>
            <span className="text-xs text-muted-foreground">{t.subject_template}</span>
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-2 rounded-md border border-border p-3">
        <p className="text-xs font-medium text-muted-foreground">{editingCode ? `Editando "${editingCode}"` : "Nueva plantilla"}</p>
        {!editingCode && (
          <div className="flex flex-col gap-1">
            <Label htmlFor="tpl-code">Código</Label>
            <Input id="tpl-code" value={form.code} onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))} placeholder="ej. welcome" />
          </div>
        )}
        <div className="flex flex-col gap-1">
          <Label htmlFor="tpl-subject">Asunto (admite {"{placeholders}"})</Label>
          <Input
            id="tpl-subject"
            value={form.subject_template}
            onChange={(e) => setForm((f) => ({ ...f, subject_template: e.target.value }))}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="tpl-body">Cuerpo (admite {"{placeholders}"})</Label>
          <textarea
            id="tpl-body"
            rows={3}
            className={TEXTAREA_CLASS}
            value={form.body_template}
            onChange={(e) => setForm((f) => ({ ...f, body_template: e.target.value }))}
          />
        </div>
        {formError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{formError}</p>}
        <div className="flex gap-2">
          <Button
            size="sm"
            disabled={!form.subject_template || !form.body_template || (!editingCode && !form.code)}
            onClick={submit}
          >
            {editingCode ? "Guardar cambios" : "Crear plantilla"}
          </Button>
          {editingCode && (
            <Button size="sm" variant="ghost" onClick={startCreate}>
              Cancelar edición
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}

function SendSection() {
  const { data: users } = useUsers();
  const { data: templates } = useNotificationTemplates();
  const sendNotification = useSendNotification();

  const [recipientId, setRecipientId] = useState("");
  const [mode, setMode] = useState<"direct" | "template">("direct");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [templateCode, setTemplateCode] = useState("");
  const [contextRaw, setContextRaw] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const [sendSuccess, setSendSuccess] = useState(false);

  const submit = async () => {
    setSendError(null);
    setSendSuccess(false);
    try {
      const context: Record<string, string> = {};
      for (const line of contextRaw.split("\n")) {
        const [k, ...rest] = line.split("=");
        if (k && rest.length) context[k.trim()] = rest.join("=").trim();
      }
      await sendNotification.mutateAsync({
        recipient_user_id: Number(recipientId),
        channel: "in_app",
        ...(mode === "direct" ? { title, body } : { template_code: templateCode, context }),
      });
      setSendSuccess(true);
      setTitle("");
      setBody("");
      setContextRaw("");
    } catch (err) {
      setSendError(err instanceof ApiError ? err.message : "No se pudo enviar la notificación");
    }
  };

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-medium text-foreground">Enviar notificación</h2>
      <div className="flex flex-col gap-2 rounded-md border border-border p-3">
        <div className="flex flex-col gap-1">
          <Label>Destinatario</Label>
          <Select value={recipientId} onValueChange={setRecipientId}>
            <SelectTrigger aria-label="Destinatario"><SelectValue placeholder="Elegí un usuario" /></SelectTrigger>
            <SelectContent>
              {users?.map((u) => <SelectItem key={u.id} value={String(u.id)}>{u.full_name ?? u.email}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <Label>Contenido</Label>
          <Select value={mode} onValueChange={(v) => setMode(v as "direct" | "template")}>
            <SelectTrigger aria-label="Modo de contenido"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="direct">Directo</SelectItem>
              <SelectItem value="template">Desde plantilla</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {mode === "direct" ? (
          <>
            <div className="flex flex-col gap-1">
              <Label htmlFor="send-title">Título</Label>
              <Input id="send-title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="send-body">Cuerpo</Label>
              <textarea id="send-body" rows={2} className={TEXTAREA_CLASS} value={body} onChange={(e) => setBody(e.target.value)} />
            </div>
          </>
        ) : (
          <>
            <div className="flex flex-col gap-1">
              <Label>Plantilla</Label>
              <Select value={templateCode} onValueChange={setTemplateCode}>
                <SelectTrigger aria-label="Plantilla"><SelectValue placeholder="Elegí una plantilla" /></SelectTrigger>
                <SelectContent>
                  {templates?.map((t) => <SelectItem key={t.id} value={t.code}>{t.code}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="send-context">Contexto (una variable por línea: nombre=valor)</Label>
              <textarea id="send-context" rows={2} className={TEXTAREA_CLASS} value={contextRaw} onChange={(e) => setContextRaw(e.target.value)} />
            </div>
          </>
        )}

        {sendError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{sendError}</p>}
        {sendSuccess && <p className="rounded-md bg-emerald-100 px-3 py-2 text-sm text-emerald-800">Notificación enviada.</p>}

        <Button
          size="sm"
          className="w-fit"
          disabled={!recipientId || (mode === "direct" ? !title || !body : !templateCode)}
          onClick={submit}
        >
          Enviar
        </Button>
      </div>
    </section>
  );
}
