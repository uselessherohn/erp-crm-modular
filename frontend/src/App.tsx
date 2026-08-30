import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { LoginPage } from "@/pages/LoginPage";
import { UsersPage } from "@/pages/UsersPage";
import { RolesPage } from "@/pages/RolesPage";
import { ContactsPage } from "@/pages/ContactsPage";
import { ProductsPage } from "@/pages/ProductsPage";
import { WarehousesPage } from "@/pages/WarehousesPage";
import { StockPage } from "@/pages/StockPage";
import { PurchaseOrdersPage } from "@/pages/PurchaseOrdersPage";
import { PriceListsPage } from "@/pages/PriceListsPage";
import { QuotesPage } from "@/pages/QuotesPage";
import { SalesOrdersPage } from "@/pages/SalesOrdersPage";
import { AccountsPage } from "@/pages/AccountsPage";
import { InvoicesPage } from "@/pages/InvoicesPage";
import { PaymentsPage } from "@/pages/PaymentsPage";
import { CreditDebitNotesPage } from "@/pages/CreditDebitNotesPage";
import { PipelinePage } from "@/pages/PipelinePage";
import { EmployeesPage } from "@/pages/EmployeesPage";
import { AppLayout } from "@/layouts/AppLayout";
import { ProtectedRoute } from "@/components/ProtectedRoute";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/contacts" replace />} />
            <Route path="/contacts" element={<ContactsPage />} />
            <Route path="/products" element={<ProductsPage />} />
            <Route path="/warehouses" element={<WarehousesPage />} />
            <Route path="/stock" element={<StockPage />} />
            <Route path="/purchase-orders" element={<PurchaseOrdersPage />} />
            <Route path="/price-lists" element={<PriceListsPage />} />
            <Route path="/quotes" element={<QuotesPage />} />
            <Route path="/sales-orders" element={<SalesOrdersPage />} />
            <Route path="/accounts" element={<AccountsPage />} />
            <Route path="/invoices" element={<InvoicesPage />} />
            <Route path="/payments" element={<PaymentsPage />} />
            <Route path="/credit-debit-notes" element={<CreditDebitNotesPage />} />
            <Route path="/pipeline" element={<PipelinePage />} />
            <Route path="/employees" element={<EmployeesPage />} />
            <Route path="/users" element={<UsersPage />} />
            <Route path="/roles" element={<RolesPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
