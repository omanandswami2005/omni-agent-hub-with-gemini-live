/**
 * Layout: AppShell — Main application shell with sidebar + content area.
 * Wraps all authenticated routes with the global VoiceProvider so voice
 * interaction persists across page navigations.
 */

import { Outlet, useNavigate } from 'react-router';
import Sidebar from '@/components/layout/Sidebar';
import TopBar from '@/components/layout/TopBar';
import MobileNav from '@/components/layout/MobileNav';
import FloatingVoiceBubble from '@/components/chat/FloatingVoiceBubble';
import MediaPreviewOverlay from '@/components/chat/MediaPreviewOverlay';
import { VoiceProvider, useVoice } from '@/hooks/useVoiceProvider';
import { useIsMobile } from '@/hooks/useMediaQuery';

export function AppShell() {
  return (
    <VoiceProvider>
      <ShellLayout />
    </VoiceProvider>
  );
}

function ShellLayout() {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const voice = useVoice();

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

      {/* Live camera / screen share PiP preview */}
      {voice.isVideoActive && (
        <MediaPreviewOverlay
          stream={voice.getPreviewStream()}
          source={voice.videoSource}
          onClose={voice.videoSource === 'screen' ? voice.toggleScreen : voice.toggleCamera}
        />
      )}

      {/* Global floating voice bubble — always visible */}
      <FloatingVoiceBubble
        isRecording={voice.isRecording}
        isMuted={voice.isMuted}
        isScreenSharing={voice.isScreenSharing}
        isCameraOn={voice.isCameraOn}
        isVideoActive={voice.isVideoActive}
        captureVolume={voice.captureVolume}
        playbackVolume={voice.playbackVolume}
        onToggleRecording={voice.toggleRecording}
        onToggleMute={voice.toggleMute}
        onToggleScreen={voice.toggleScreen}
        onToggleCamera={voice.toggleCamera}
        onOpenChat={() => navigate('/')}
        isConnected={voice.isConnected}
      />
    </div>
  );
}

export default AppShell;
