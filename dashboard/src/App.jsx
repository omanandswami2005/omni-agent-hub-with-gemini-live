import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import LoadingSpinner from '@/components/shared/LoadingSpinner';

const LoginPage = lazy(() => import('@/components/auth/LoginPage'));
const RegisterPage = lazy(() => import('@/components/auth/RegisterPage'));
const DashboardPage = lazy(() => import('@/pages/DashboardPage'));
const PersonasPage = lazy(() => import('@/pages/PersonasPage'));
const MCPStorePage = lazy(() => import('@/pages/MCPStorePage'));
const SessionsPage = lazy(() => import('@/pages/SessionsPage'));
const ClientsPage = lazy(() => import('@/pages/ClientsPage'));
const GalleryPage = lazy(() => import('@/pages/GalleryPage'));
const SettingsPage = lazy(() => import('@/pages/SettingsPage'));
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'));

function PageFallback() {
  return (
    <div className="flex h-[60vh] items-center justify-center">
      <LoadingSpinner size="lg" />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<AuthGuard />}>
            <Route element={<AppShell />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/session/:sessionId" element={<DashboardPage />} />
              <Route path="/personas" element={<PersonasPage />} />
              <Route path="/mcp-store" element={<MCPStorePage />} />
              <Route path="/sessions" element={<SessionsPage />} />
              <Route path="/clients" element={<ClientsPage />} />
              <Route path="/gallery" element={<GalleryPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
