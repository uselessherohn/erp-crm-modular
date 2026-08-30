import { Navigate } from "react-router-dom";
import { useIsAuthenticated } from "@/hooks/use-auth";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const authenticated = useIsAuthenticated();
  if (!authenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
