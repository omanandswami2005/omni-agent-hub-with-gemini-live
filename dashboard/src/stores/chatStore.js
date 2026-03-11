import { create } from 'zustand';

let _msgId = 0;
const nextId = () => `msg_${Date.now()}_${++_msgId}`;

export const useChatStore = create((set, get) => ({
  messages: [],
  transcript: { input: '', output: '' },
  agentState: 'idle', // idle, listening, processing, speaking, error
  activeTools: new Set(),

  addMessage: (msg) =>
    set((s) => ({
      messages: [...s.messages, { id: nextId(), timestamp: new Date().toISOString(), ...msg }],
    })),
  clearMessages: () => set({ messages: [] }),

  /**
   * Handle transcription events from the WebSocket.
   * While `finished` is false, update the live transcript overlay.
   * When `finished` is true, commit the transcript as a chat message.
   */
  updateTranscript: (msg) => {
    if (msg.finished) {
      const direction = msg.direction; // 'input' | 'output'
      const role = direction === 'input' ? 'user' : 'assistant';
      const text = msg.text?.trim();
      if (text) {
        get().addMessage({ role, content: text, source: 'voice' });
      }
      // Clear the live transcript for this direction
      set((s) => ({
        transcript: { ...s.transcript, [direction]: '' },
      }));
    } else {
      set((s) => ({
        transcript: { ...s.transcript, [msg.direction]: msg.text },
      }));
    }
  },

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
