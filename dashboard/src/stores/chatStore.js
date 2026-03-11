import { create } from 'zustand';

export const useChatStore = create((set, _get) => ({
  messages: [],
  transcript: { input: '', output: '' },
  agentState: 'idle', // idle, listening, processing, speaking, error
  activeTools: new Set(),

  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  clearMessages: () => set({ messages: [] }),

  updateTranscript: (msg) =>
    set((s) => ({
      transcript: { ...s.transcript, [msg.direction]: msg.text },
    })),

  setAgentState: (state) => set({ agentState: state }),

  setToolActive: (tool, active) =>
    set((s) => {
      const tools = new Set(s.activeTools);
      active ? tools.add(tool) : tools.delete(tool);
      return { activeTools: tools };
    }),

  // Audio queue for playback
  audioQueue: [],
  enqueueAudio: (blob) =>
    set((s) => ({ audioQueue: [...s.audioQueue, blob] })),
  dequeueAudio: () =>
    set((s) => ({ audioQueue: s.audioQueue.slice(1) })),
  clearAudioQueue: () => set({ audioQueue: [] }),
}));
