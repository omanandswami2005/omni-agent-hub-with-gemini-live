/**
 * Page: DashboardPage — Main dashboard with chat panel and activity overview.
 */

import { useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import ChatPanel from '@/components/chat/ChatPanel';
import GenUIRenderer from '@/components/genui/GenUIRenderer';
import PersonaCard from '@/components/persona/PersonaCard';
import ClientStatusBar from '@/components/clients/ClientStatusBar';
import PipelineMonitor from '@/components/chat/PipelineMonitor';
import { useVoice } from '@/hooks/useVoiceProvider';
import { useChatStore } from '@/stores/chatStore';
import { useSessionStore } from '@/stores/sessionStore';
import { usePersonaStore } from '@/stores/personaStore';
import { useClientStore } from '@/stores/clientStore';

export default function DashboardPage() {
    useDocumentTitle('Dashboard');
    const voice = useVoice();
    const navigate = useNavigate();
    const { sessionId } = useParams();
    const loadMessages = useSessionStore((s) => s.loadMessages);
    const switchSession = useSessionStore((s) => s.switchSession);
    const messagesLoading = useSessionStore((s) => s.messagesLoading);
    const addMessage = useChatStore((s) => s.addMessage);
    const clearMessages = useChatStore((s) => s.clearMessages);
    const loadedRef = useRef(null);

    // When the chat WS connects and the server assigns a session,
    // navigate to /session/:id so the URL reflects the active session
    useEffect(() => {
        if (voice.serverSessionId && !sessionId) {
            navigate(`/session/${voice.serverSessionId}`, { replace: true });
        }
    }, [voice.serverSessionId, sessionId, navigate]);

    // Load session messages when URL sessionId changes
    useEffect(() => {
        if (!sessionId || sessionId === loadedRef.current) return;
        loadedRef.current = sessionId;
        switchSession(sessionId);
        clearMessages();
        loadMessages(sessionId).then((msgs) => {
            msgs.forEach((m) => addMessage({ role: m.role, content: m.content, source: m.source || 'history' }));
        });
    }, [sessionId, loadMessages, switchSession, clearMessages, addMessage]);

    const messages = useChatStore((s) => s.messages);
    const activePersona = usePersonaStore((s) => s.activePersona);
    const setActivePersona = usePersonaStore((s) => s.setActivePersona);
    const personas = usePersonaStore((s) => s.personas);
    const clients = useClientStore((s) => s.clients);
    const activeTools = useChatStore((s) => s.activeTools);

    // Find the last genui message for the side panel
    const lastGenUI = [...messages].reverse().find((m) => m.genui_type);

    return (
        <div className="flex h-full gap-4">
            {/* Main chat panel */}
            <div className="flex-1">
                <ChatPanel
                    onSend={voice.sendText}
                    isRecording={voice.isRecording}
                    captureVolume={voice.captureVolume}
                    playbackVolume={voice.playbackVolume}
                    isChatConnected={voice.isConnected}
                />
            </div>

            {/* Right sidebar */}
            <aside className="hidden w-80 space-y-4 overflow-y-auto p-4 lg:block">
                {/* Connection status */}
                <div className="rounded-lg border border-border p-3">
                    <p className="mb-1 text-xs font-medium text-muted-foreground">Status</p>
                    <div className="space-y-1.5">
                        <div className="flex items-center gap-2">
                            <span className={`h-2 w-2 rounded-full ${voice.isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
                            <span className="text-sm">{voice.isConnected ? 'Connected' : 'Disconnected'}</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className={`h-2 w-2 rounded-full ${voice.voiceEnabled ? 'bg-blue-500' : 'bg-muted-foreground'}`} />
                            <span className="text-sm">Voice {voice.voiceEnabled ? 'On' : 'Off'}</span>
                        </div>
                    </div>
                </div>

                {/* Active persona */}
                {activePersona && (
                    <div>
                        <p className="mb-2 text-xs font-medium text-muted-foreground">Active Persona</p>
                        <PersonaCard persona={activePersona} isActive />
                    </div>
                )}

                {/* Quick persona switch */}
                {personas.length > 1 && (
                    <div>
                        <p className="mb-2 text-xs font-medium text-muted-foreground">Switch Persona</p>
                        <div className="space-y-1">
                            {personas.filter((p) => p !== activePersona).slice(0, 3).map((p) => (
                                <PersonaCard key={p.id || p.name} persona={p} onSelect={setActivePersona} />
                            ))}
                        </div>
                    </div>
                )}

                {/* Connected clients */}
                {clients.length > 0 && (
                    <div>
                        <p className="mb-2 text-xs font-medium text-muted-foreground">Clients</p>
                        <ClientStatusBar clients={clients} />
                    </div>
                )}

                {/* Active tools */}
                {activeTools.size > 0 && (
                    <div className="rounded-lg border border-border p-3">
                        <p className="mb-1 text-xs font-medium text-muted-foreground">Active Tools</p>
                        <div className="flex flex-wrap gap-1">
                            {[...activeTools].map((tool) => (
                                <span key={tool} className="rounded bg-primary/10 px-2 py-0.5 text-xs text-primary">{tool}</span>
                            ))}
                        </div>
                    </div>
                )}

                {/* Pipeline monitor */}
                <PipelineMonitor />

                {/* GenUI preview */}
                {lastGenUI && (
                    <div>
                        <p className="mb-2 text-xs font-medium text-muted-foreground">Generated UI</p>
                        <GenUIRenderer type={lastGenUI.genui_type} data={lastGenUI.genui_data} />
                    </div>
                )}
            </aside>
        </div>
    );
}
