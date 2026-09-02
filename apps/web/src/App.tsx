import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AdminDesk } from "./pages/AdminDesk";
import { ClientDesk } from "./pages/ClientDesk";
import { Login } from "./pages/Login";
import { loadSession } from "./session";
import type { Session } from "./api";

function Guard({
  session,
  roles,
  children,
}: {
  session: Session | null;
  roles: Session["role"][];
  children: ReactNode;
}) {
  if (!session) return <Navigate to="/" replace />;
  if (!roles.includes(session.role)) {
    return <Navigate to={session.role === "client" ? "/desk" : "/admin"} replace />;
  }
  return <>{children}</>;
}

export function App() {
  const session = loadSession();
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route
        path="/desk"
        element={
          <Guard session={session} roles={["client"]}>
            <ClientDesk />
          </Guard>
        }
      />
      <Route
        path="/admin"
        element={
          <Guard session={session} roles={["ops", "cto"]}>
            <AdminDesk />
          </Guard>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
