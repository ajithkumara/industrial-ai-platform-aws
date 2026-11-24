import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import DashboardPage from "@/pages/Dashboard";
import LiveMapPage from "@/pages/LiveMap";
import VehiclesPage from "@/pages/Vehicles";
import VehicleDetailPage from "@/pages/VehicleDetail";
import DriversPage from "@/pages/Drivers";
import DriverDetailPage from "@/pages/DriverDetail";
import TripsPage from "@/pages/Trips";
import TripDetailPage from "@/pages/TripDetail";
import GeofencesPage from "@/pages/Geofences";
import HealthPage from "@/pages/Health";
import MaintenancePage from "@/pages/Maintenance";
import FuelPage from "@/pages/Fuel";
import SafetyPage from "@/pages/Safety";
import AnalyticsPage from "@/pages/Analytics";
import AssistantPage from "@/pages/Assistant";
import ReportsPage from "@/pages/Reports";
import IntegrationsPage from "@/pages/Integrations";
import NotificationsPage from "@/pages/Notifications";
import SettingsPage from "@/pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/map" element={<LiveMapPage />} />
        <Route path="/vehicles" element={<VehiclesPage />} />
        <Route path="/vehicles/:id" element={<VehicleDetailPage />} />
        <Route path="/drivers" element={<DriversPage />} />
        <Route path="/drivers/:id" element={<DriverDetailPage />} />
        <Route path="/trips" element={<TripsPage />} />
        <Route path="/trips/:id" element={<TripDetailPage />} />
        <Route path="/geofences" element={<GeofencesPage />} />
        <Route path="/health" element={<HealthPage />} />
        <Route path="/maintenance" element={<MaintenancePage />} />
        <Route path="/fuel" element={<FuelPage />} />
        <Route path="/safety" element={<SafetyPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/assistant" element={<AssistantPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/integrations" element={<IntegrationsPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
