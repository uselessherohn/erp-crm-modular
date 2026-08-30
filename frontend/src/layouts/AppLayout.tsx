import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useCurrentUser, useLogout } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Users, ShieldCheck, LogOut, Contact, Package, Warehouse, Boxes, ClipboardList, Tags, FileText, ShoppingCart, Landmark, Receipt, Wallet, FileMinus, GitBranch, IdCard } from "lucide-react";

// El menú se muestra igual para todos los usuarios autenticados — el
// backend ya aplica RBAC (403 si falta el permiso); no duplicamos esa
// lógica en el cliente todavía. Si más adelante /users/me expone
// permisos efectivos, esto se puede filtrar client-side también.
const NAV_ITEMS = [
  { to: "/contacts", label: "Contactos", icon: Contact },
  { to: "/products", label: "Productos", icon: Package },
  { to: "/warehouses", label: "Almacenes", icon: Warehouse },
  { to: "/stock", label: "Stock", icon: Boxes },
  { to: "/purchase-orders", label: "Compras", icon: ClipboardList },
  { to: "/price-lists", label: "Precios", icon: Tags },
  { to: "/quotes", label: "Cotizaciones", icon: FileText },
  { to: "/sales-orders", label: "Ventas", icon: ShoppingCart },
  { to: "/accounts", label: "Contabilidad", icon: Landmark },
  { to: "/invoices", label: "Facturación", icon: Receipt },
  { to: "/payments", label: "Pagos", icon: Wallet },
  { to: "/credit-debit-notes", label: "Notas C/D", icon: FileMinus },
  { to: "/pipeline", label: "Pipeline", icon: GitBranch },
  { to: "/employees", label: "Recursos Humanos", icon: IdCard },
  { to: "/users", label: "Usuarios", icon: Users },
  { to: "/roles", label: "Roles", icon: ShieldCheck },
];

export function AppLayout() {
  const navigate = useNavigate();
  const { data: user } = useCurrentUser();
  const logout = useLogout();

  const handleLogout = async () => {
    await logout.mutateAsync();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 flex-col border-r border-border bg-card">
        <div className="flex items-center gap-2 border-b border-border px-4 py-5">
          <img src="/axis-suite-icon.svg" alt="" className="size-7 shrink-0" />
          <span className="font-display text-lg font-medium text-primary" style={{ fontFamily: "var(--font-display)" }}>
            Axis Suite
          </span>
        </div>
        <nav className="flex-1 space-y-1 p-3">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-foreground/80 hover:bg-muted",
                  isActive && "bg-secondary text-secondary-foreground"
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-border p-3">
          <p className="truncate px-3 text-xs text-muted-foreground">{user?.email}</p>
          <Button variant="ghost" size="sm" className="mt-1 w-full justify-start gap-2" onClick={handleLogout}>
            <LogOut className="size-4" />
            Cerrar sesión
          </Button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto p-8">
        <Outlet />
      </main>
    </div>
  );
}
