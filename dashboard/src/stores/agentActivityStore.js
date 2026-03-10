import { create } from 'zustand';

/**
 * Agent Activity Store - Manages async agent activities in real-time
 * 
 * Tracks:
 * - Sub-agent calls
 * - Reasoning steps
 * - MCP tool invocations
 * - Background tool executions
 * - Progress updates
 */

export const useAgentActivityStore = create((set, get) => ({
  // All activities in current session
  activities: [],
  
  // Whether to show in chat (toggle)
  showInChat: true,
  
  // Add new activity
  addActivity: (activity) => {
    const newActivity = {
      ...activity,
      id: Date.now() + Math.random(),
      timestamp: new Date().toISOString(),
    };
    set((state) => ({
      activities: [...state.activities, newActivity],
    }));
    return newActivity.id;
  },
  
  // Update activity status
  updateActivity: (id, updates) => {
    set((state) => ({
      activities: state.activities.map((a) =>
        a.id === id ? { ...a, ...updates } : a
      ),
    }));
  },
  
  // Complete activity
  completeActivity: (id, result) => {
    set((state) => ({
      activities: state.activities.map((a) =>
        a.id === id
          ? { ...a, status: 'completed', result, timestamp: new Date().toISOString() }
          : a
      ),
    }));
  },
  
  // Fail activity
  failActivity: (id, error) => {
    set((state) => ({
      activities: state.activities.map((a) =>
        a.id === id
          ? { ...a, status: 'failed', error, timestamp: new Date().toISOString() }
          : a
      ),
    }));
  },
  
  // Add sub-agent call activity
  addSubAgentCall: (parentAgent, subAgent, task) => {
    return get().addActivity({
      activity_type: 'sub_agent_call',
      title: `Calling ${subAgent}`,
      details: `Delegating: ${task}`,
      status: 'started',
      parent_agent: parentAgent,
    });
  },
  
  // Add reasoning activity
  addReasoning: (agent, thought) => {
    return get().addActivity({
      activity_type: 'reasoning',
      title: 'Reasoning',
      details: thought,
      status: 'in_progress',
      parent_agent: agent,
    });
  },
  
  // Add MCP call activity
  addMCPCall: (agent, mcpName, toolName) => {
    return get().addActivity({
      activity_type: 'mcp_call',
      title: `MCP: ${mcpName}`,
      details: `Calling tool: ${toolName}`,
      status: 'started',
      parent_agent: agent,
    });
  },
  
  // Add tool call activity
  addToolCall: (agent, toolName, args = {}) => {
    return get().addActivity({
      activity_type: 'tool_call',
      title: `Tool: ${toolName}`,
      details: args ? JSON.stringify(args).slice(0, 100) : '',
      status: 'started',
      parent_agent: agent,
    });
  },
  
  // Add waiting activity
  addWaiting: (agent, reason) => {
    return get().addActivity({
      activity_type: 'waiting',
      title: 'Waiting',
      details: reason,
      status: 'in_progress',
      parent_agent: agent,
    });
  },
  
  // Toggle show in chat
  setShowInChat: (show) => set({ showInChat: show }),
  
  // Clear all activities (on new session)
  clear: () => set({ activities: [] }),
  
  // Get activities by type
  getByType: (type) => get().activities.filter((a) => a.activity_type === type),
  
  // Get in-progress activities
  getInProgress: () => get().activities.filter((a) => 
    a.status === 'started' || a.status === 'in_progress'
  ),
}));
