import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { CheckPage } from "@/pages/CheckPage";
import { EntitiesPage } from "@/pages/EntitiesPage";
import { EntityPage } from "@/pages/EntityPage";
import { FindingPage } from "@/pages/FindingPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { RegistryPage } from "@/pages/RegistryPage";
import { ReviewPage } from "@/pages/ReviewPage";
import { SensitivityPage } from "@/pages/SensitivityPage";
import { SourcesPage } from "@/pages/SourcesPage";

/** Routes; "Sprawdź" is the landing page. */
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/sprawdz" replace />} />
        <Route path="sprawdz" element={<CheckPage />} />
        <Route path="zgloszenia" element={<ReviewPage />} />
        <Route path="zgloszenia/:id" element={<FindingPage />} />
        <Route path="podmioty" element={<EntitiesPage />} />
        <Route path="podmioty/:key" element={<EntityPage />} />
        <Route path="monitoring" element={<SourcesPage />} />
        <Route path="czulosc" element={<SensitivityPage />} />
        <Route path="rejestr" element={<RegistryPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
