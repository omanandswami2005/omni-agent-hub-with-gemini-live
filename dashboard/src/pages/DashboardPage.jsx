/**
 * Page: DashboardPage — Main dashboard with chat panel and activity overview.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import ChatPanel from '@/components/chat/ChatPanel';
import GenUIModal from '@/components/genui/GenUIModal';
import CustomSelect from '@/components/shared/CustomSelect';
import PersonaCard from '@/components/persona/PersonaCard';
import ClientStatusBar from '@/components/clients/ClientStatusBar';
import PipelineMonitor from '@/components/chat/PipelineMonitor';
import TaskPanel from '@/components/chat/TaskPanel';
import DesktopViewer from '@/components/sandbox/DesktopViewer';
import { useVoice } from '@/hooks/useVoiceProvider';
import { useChatStore } from '@/stores/chatStore';
import { useSessionStore } from '@/stores/sessionStore';
import { usePersonaStore } from '@/stores/personaStore';
import { useClientStore } from '@/stores/clientStore';
import { usePipelineStore } from '@/stores/pipelineStore';
import { useTaskStore } from '@/stores/taskStore';

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
    const setLoadingHistory = useChatStore((s) => s.setLoadingHistory);
    const loadedRef = useRef(null);
    const loadGenRef = useRef(0); // version counter to prevent session-switch race

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
        const gen = ++loadGenRef.current;
        switchSession(sessionId);
        setLoadingHistory(true);
        clearMessages();
        loadMessages(sessionId).then((msgs) => {
            // Stale — user already switched to a different session
            if (loadGenRef.current !== gen) return;
            msgs.forEach((m) => addMessage({
                role: m.role,
                content: m.content,
                type: m.type || 'text',
                source: m.source || 'history',
                content_type: m.content_type || 'text',
                genui_type: m.genui_type || undefined,
                genui_data: m.genui_data || undefined,
                tool_name: m.tool_name,
                arguments: m.arguments,
                action_kind: m.action_kind || '',
                source_label: m.source_label || '',
                success: m.success,
                result: m.result || '',
                responded: m.responded || false,
                image_url: m.image_url || '',
                description: m.description || '',
                text: m.type === 'image' ? (m.description || m.content || '') : undefined,
                images: m.images || [],
                parts: m.parts || [],
            }));
        }).catch((err) => {
            if (loadGenRef.current !== gen) return;
            if (err?.status === 404) navigate('/dashboard');
        }).finally(() => {
            if (loadGenRef.current === gen) setLoadingHistory(false);
        });
    }, [sessionId, loadMessages, switchSession, clearMessages, addMessage, setLoadingHistory]);

    const messages = useChatStore((s) => s.messages);
    const activePersona = usePersonaStore((s) => s.activePersona);
    const setActivePersona = usePersonaStore((s) => s.setActivePersona);
    const personas = usePersonaStore((s) => s.personas);
    const clients = useClientStore((s) => s.clients);
    const activeTools = useChatStore((s) => s.activeTools);

    const [sidebarTab, setSidebarTab] = useState('overview');
    const activePipeline = usePipelineStore((s) => s.pipeline);
    const pipelineHistory = usePipelineStore((s) => s.history);
    const hasPipeline = !!activePipeline || pipelineHistory.length > 0;
    const desktop = useTaskStore((s) => s.desktop);
    const tasks = useTaskStore((s) => s.tasks);
    const taskList = useMemo(() => Object.values(tasks).sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')), [tasks]);
    const hasRunningTask = useMemo(() => Object.values(tasks).some((t) => t.status === 'running'), [tasks]);
    const hasTasks = taskList.length > 0;
    const hasActivity = hasPipeline || hasTasks;

    // Auto-switch to pipeline tab when a pipeline starts or task is created
    useEffect(() => {
        if (activePipeline) setSidebarTab('pipeline');
    }, [activePipeline?.pipeline_id]);

    useEffect(() => {
        if (hasRunningTask || taskList.length === 1) setSidebarTab('pipeline');
    }, [hasRunningTask, taskList.length]);

    // When persona changes, reconnect WS so the backend uses the new persona's voice
    const reconnect = useVoice((v) => v.reconnect);
    const prevPersonaRef = useRef(null);
    useEffect(() => {
        if (activePersona?.id && prevPersonaRef.current && activePersona.id !== prevPersonaRef.current) {
            reconnect?.();
        }
        prevPersonaRef.current = activePersona?.id;
    }, [activePersona?.id, reconnect]);

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
            <aside className="hidden w-80 flex-col overflow-y-auto lg:flex">
                {/* Tab nav */}
                <div className="flex shrink-0 gap-1 border-b border-white/[0.06] px-1 pb-2 pt-1">
                    <button
                        onClick={() => setSidebarTab('overview')}
                        className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${sidebarTab === 'overview'
                            ? 'bg-foreground text-background'
                            : 'text-muted-foreground hover:bg-white/[0.04]'
                            }`}
                    >
                        Overview
                    </button>
                    <button
                        onClick={() => setSidebarTab('pipeline')}
                        className={`relative flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${sidebarTab === 'pipeline'
                            ? 'bg-foreground text-background'
                            : 'text-muted-foreground hover:bg-white/[0.04]'
                            }`}
                    >
                        Tasks
                        {hasActivity && sidebarTab !== 'pipeline' && (
                            <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-blue-400" />
                        )}
                        {(activePipeline || hasRunningTask) && (
                            <span className="ml-1.5 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                        )}
                    </button>
                    <button
                        onClick={() => setSidebarTab('desktop')}
                        className={`relative flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${sidebarTab === 'desktop'
                            ? 'bg-foreground text-background'
                            : 'text-muted-foreground hover:bg-white/[0.04]'
                            }`}
                    >
                        Desktop
                        {desktop?.status === 'running' && (
                            <span className="ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />
                        )}
                    </button>
                </div>

                {sidebarTab === 'overview' ? (
                    <div className="space-y-4 overflow-y-auto p-4">
                        {/* Connection status */}
                        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                            <p className="mb-1 text-xs font-medium text-muted-foreground">Status</p>
                            <div className="space-y-1.5">
                                <div className="flex items-center gap-2">
                                    <span className={`h-2 w-2 rounded-full ${voice.isConnected ? 'bg-emerald-400' : 'bg-red-400'}`} />
                                    <span className="text-sm">{voice.isConnected ? 'Connected' : 'Disconnected'}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className={`h-2 w-2 rounded-full ${voice.voiceEnabled ? 'bg-blue-400' : 'bg-muted-foreground'}`} />
                                    <span className="text-sm">Voice {voice.voiceEnabled ? 'On' : 'Off'}</span>
                                </div>
                            </div>
                        </div>

                        {/* Active persona + switcher */}
                        {activePersona && (
                            <div>
                                <p className="mb-2 text-xs font-medium text-muted-foreground">Active Persona</p>
                                <PersonaCard persona={activePersona} isActive />
                                {personas.length > 1 && (
                                    <CustomSelect
                                        value={activePersona.id}
                                        options={personas.map((p) => ({
                                            value: p.id,
                                            label: `${p.name} — ${p.voice || 'default voice'}`,
                                        }))}
                                        onChange={(id) => {
                                            const p = personas.find((p) => p.id === id);
                                            if (p) setActivePersona(p);
                                        }}
                                        className="mt-2"
                                    />
                                )}
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
                            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                                <p className="mb-1 text-xs font-medium text-muted-foreground">Active Tools</p>
                                <div className="flex flex-wrap gap-1">
                                    {[...activeTools].map((tool) => (
                                        <span key={tool} className="rounded-lg bg-white/[0.04] border border-white/[0.06] px-2 py-0.5 text-xs text-foreground/70">{tool}</span>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* GenUI preview */}
                        {lastGenUI && (
                            <div>
                                <p className="mb-2 text-xs font-medium text-muted-foreground">Generated UI</p>
                                <GenUIModal type={lastGenUI.genui_type} data={lastGenUI.genui_data} />
                            </div>
                        )}
                    </div>
                ) : sidebarTab === 'desktop' ? (
                    <div className="overflow-y-auto p-4">
                        <DesktopViewer />
                    </div>
                ) : (
                    <div className="overflow-y-auto p-4 space-y-4">
                        <TaskPanel />
                        {hasPipeline && <PipelineMonitor />}
                        {!hasActivity && (
                            <div className="mt-4 rounded-xl border border-dashed border-white/[0.08] bg-white/[0.01] p-6 text-center">
                                <p className="text-sm font-medium text-muted-foreground">No tasks yet</p>
                                <p className="mt-1 text-xs text-muted-foreground/60">
                                    Ask for a complex multi-step task to trigger the planner.
                                </p>
                            </div>
                        )}
                    </div>
                )}
            </aside>
        </div>
    );
}
