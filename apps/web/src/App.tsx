import { Navigate, Route, Routes } from "react-router-dom";
import { AdminDesk } from "./pages/AdminDesk";
import { Swap } from "./pages/Swap";
import { loadSession } from "./session";

export function App() {
  const session = loadSession();
  return (
    <Routes>
      <Route path="/" element={<Swap />} />
      <Route
        path="/admin"
        element={session && session.role !== "client" ? <AdminDesk /> : <Navigate to="/" replace />}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
