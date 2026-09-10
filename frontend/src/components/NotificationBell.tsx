import { Bell } from "lucide-react";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { useNotifications, useMarkNotificationRead, useMarkAllNotificationsRead } from "@/hooks/use-notifications";
import { cn } from "@/lib/utils";

function timeAgo(dateString: string): string {
  const diffMs = Date.now() - new Date(dateString).getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "ahora";
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  return new Date(dateString).toLocaleDateString();
}

export function NotificationBell() {
  // Poll simple cada 30s — sin WebSocket/SSE en este cierre (fuera de
  // alcance del DoD de este módulo; TODO si se necesita push real-time).
  const { data: notifications } = useNotifications({ pollMs: 30_000 });
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();

  const unreadCount = (notifications ?? []).filter((n) => !n.read_at).length;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="relative size-9 p-0" aria-label="Notificaciones">
          <Bell className="size-5" />
          {unreadCount > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-destructive text-[10px] font-medium text-destructive-foreground">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent>
        <div className="flex items-center justify-between px-2 py-1.5">
          <p className="text-sm font-medium text-foreground">Notificaciones</p>
          {unreadCount > 0 && (
            <Button variant="ghost" size="sm" className="h-auto p-0 text-xs" onClick={() => markAllRead.mutate()}>
              Marcar todas como leídas
            </Button>
          )}
        </div>
        <div className="flex max-h-80 flex-col gap-1 overflow-y-auto">
          {(notifications ?? []).length === 0 && (
            <p className="px-2 py-4 text-center text-sm text-muted-foreground">Sin notificaciones.</p>
          )}
          {(notifications ?? []).map((n) => (
            <button
              key={n.id}
              onClick={() => !n.read_at && markRead.mutate(n.id)}
              className={cn(
                "flex flex-col gap-0.5 rounded-md px-2 py-2 text-left text-sm hover:bg-muted",
                !n.read_at && "bg-primary/5"
              )}
            >
              <div className="flex items-center gap-1.5">
                {!n.read_at && <span className="size-1.5 shrink-0 rounded-full bg-primary" />}
                <span className={cn("font-medium text-foreground", n.read_at && "font-normal")}>{n.title}</span>
              </div>
              <p className="text-xs text-muted-foreground">{n.body}</p>
              <span className="text-[10px] text-muted-foreground">{timeAgo(n.created_at)}</span>
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
