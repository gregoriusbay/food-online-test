import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ReceiptsPage from "./pages/ReceiptsPage";
import ReceiptDetailPage from "./pages/ReceiptDetailPage";
import AskPage from "./pages/AskPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/receipts" replace />} />
          <Route path="receipts" element={<ReceiptsPage />} />
          <Route path="receipts/:id" element={<ReceiptDetailPage />} />
          <Route path="ask" element={<AskPage />} />
          <Route path="*" element={<Navigate to="/receipts" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
