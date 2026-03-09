import { BrowserRouter, Routes, Route } from 'react-router';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import DashboardPage from '@/pages/DashboardPage';
import PersonasPage from '@/pages/PersonasPage';
import MCPStorePage from '@/pages/MCPStorePage';
import SessionsPage from '@/pages/SessionsPage';
import SettingsPage from '@/pages/SettingsPage';
import ClientsPage from '@/pages/ClientsPage';
import NotFoundPage from '@/pages/NotFoundPage';
import { LoginPage } from '@/components/auth/LoginPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<AuthGuard />}>
          <Route element={<AppShell />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/personas" element={<PersonasPage />} />
            <Route path="/mcp-store" element={<MCPStorePage />} />
            <Route path="/sessions" element={<SessionsPage />} />
            <Route path="/clients" element={<ClientsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
}
