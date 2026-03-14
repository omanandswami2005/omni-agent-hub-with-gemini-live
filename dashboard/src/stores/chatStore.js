import { create } from 'zustand';

let _msgId = 0;
const nextId = () => `msg_${Date.now()}_${++_msgId}`;

export const useChatStore = create((set, get) => ({
  messages: [],
  transcript: { input: '', output: '' },
  // Live transcript for audio coming from another device (cross-client relay)
  crossTranscript: { input: '', output: '' },
  agentState: 'idle', // idle, listening, processing, speaking, error
  activeTools: new Set(),

  addMessage: (msg) =>
    set((s) => ({
      messages: [...s.messages, { id: nextId(), timestamp: new Date().toISOString(), ...msg }],
    })),
  clearMessages: () => set({ messages: [] }),

  /**
   * Add an action (tool_call) as a message. Returns the message id so
   * the matching tool_response can update the same entry via completeAction.
   */
  addAction: (action) => {
    const id = nextId();
    set((s) => ({
      messages: [
        ...s.messages,
        { id, timestamp: new Date().toISOString(), role: 'system', type: 'action', responded: false, ...action },
      ],
    }));
    return id;
  },

  /**
   * Merge a tool_response into its matching tool_call action in-place.
   * Finds the last unresponded action with the same tool_name.
   */
  completeAction: (tool_name, response) => {
    set((s) => {
      const msgs = [...s.messages];
      // Find the last unresponded action with this tool_name
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].type === 'action' && msgs[i].tool_name === tool_name && !msgs[i].responded) {
          msgs[i] = { ...msgs[i], ...response, responded: true };
          break;
        }
      }
      return { messages: msgs };
    });
  },

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

  /**
   * Handle transcription events relayed from another device.
   * Partials update the crossTranscript overlay; final commit adds a message.
   */
  updateCrossClientTranscript: (msg) => {
    if (msg.finished) {
      const direction = msg.direction;
      const role = direction === 'input' ? 'user' : 'assistant';
      const text = msg.text?.trim();
      if (text) {
        get().addMessage({ role, content: text, source: 'voice', cross_client: true });
      }
      set((s) => ({
        crossTranscript: { ...s.crossTranscript, [direction]: '' },
      }));
    } else {
      set((s) => ({
        crossTranscript: { ...s.crossTranscript, [msg.direction]: msg.text },
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

  /** Mark all unresponded actions as cancelled (for interruptions) */
  cancelAllActions: () =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.type === 'action' && !m.responded
          ? { ...m, responded: true, success: false, result: 'Cancelled' }
          : m
      ),
      activeTools: new Set(),
    })),

  // Audio queue for playback
  audioQueue: [],
  voiceOutputEnabled: true,
  setVoiceOutputEnabled: (enabled) => set({ voiceOutputEnabled: enabled }),
  enqueueAudio: (blob) => {
    if (!get().voiceOutputEnabled) return; // Skip audio when voice output is off
    set((s) => ({ audioQueue: [...s.audioQueue, blob] }));
  },
  dequeueAudio: () =>
    set((s) => ({ audioQueue: s.audioQueue.slice(1) })),
  clearAudioQueue: () => set({ audioQueue: [] }),
}));
