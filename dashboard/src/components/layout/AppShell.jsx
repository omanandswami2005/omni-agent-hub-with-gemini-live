/**
 * Layout: AppShell — Main application shell with sidebar + content area.
 */

import { Outlet } from 'react-router';
import Sidebar from '@/components/layout/Sidebar';
import TopBar from '@/components/layout/TopBar';
import MobileNav from '@/components/layout/MobileNav';
import { useIsMobile } from '@/hooks/useMediaQuery';

export function AppShell() {
  const isMobile = useIsMobile();

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-4 pb-20 md:pb-4">
          <Outlet />
        </main>
      </div>
      {isMobile && <MobileNav />}
    </div>
  );
}

export default AppShell;
