/**
 * Agent Activity Panel - Shows async agent actions in real-time
 * 
 * Features:
 * - Displays sub-agent calls, reasoning, MCP invocations, tool calls
 * - Collapsible in main chat
 * - Separate panel mode
 * - Toggle to show/hide in chat
 */

import { useState } from 'react';
import { cn } from '@/lib/cn';

const ACTIVITY_ICONS = {
  sub_agent_call: '🤖',
  reasoning: '🧠',
  mcp_call: '🔌',
  tool_call: '⚙️',
  waiting: '⏳',
  completed: '✅',
  failed: '❌',
};

const ACTIVITY_COLORS = {
  started: 'border-blue-500 bg-blue-50',
  in_progress: 'border-amber-500 bg-amber-50',
  completed: 'border-green-500 bg-green-50',
  failed: 'border-red-500 bg-red-50',
};

export function AgentActivityPanel({ activities = [], className }) {
  const [isExpanded, setIsExpanded] = useState(true);

  if (activities.length === 0) {
    return null;
  }

  return (
    <div className={cn("rounded-lg border border-border bg-background", className)}>
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center justify-between px-4 py-2 text-left hover:bg-muted/50"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Agent Activity</span>
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs">
            {activities.length}
          </span>
        </div>
        <span className="text-muted-foreground">
          {isExpanded ? '▼' : '▶'}
        </span>
      </button>

      {/* Activity List */}
      {isExpanded && (
        <div className="max-h-64 overflow-y-auto px-4 pb-4">
          {activities.map((activity, index) => (
            <ActivityItem key={index} activity={activity} />
          ))}
        </div>
      )}
    </div>
  );
}

function ActivityItem({ activity }) {
  const icon = ACTIVITY_ICONS[activity.activity_type] || '📋';
  const colorClass = ACTIVITY_COLORS[activity.status] || 'border-gray-500';
  
  return (
    <div className={cn(
      "mb-2 rounded border-l-4 p-3",
      colorClass,
      "bg-muted/30"
    )}>
      <div className="flex items-start gap-2">
        <span className="text-lg">{icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm">{activity.title}</span>
            {activity.parent_agent && (
              <span className="text-xs text-muted-foreground">
                via {activity.parent_agent}
              </span>
            )}
          </div>
          {activity.details && (
            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
              {activity.details}
            </p>
          )}
          {activity.progress > 0 && activity.progress < 1 && (
            <div className="mt-2 h-1 w-full rounded-full bg-muted">
              <div 
                className="h-1 rounded-full bg-primary transition-all"
                style={{ width: `${activity.progress * 100}%` }}
              />
            </div>
          )}
        </div>
        <StatusBadge status={activity.status} />
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  const styles = {
    started: 'bg-blue-100 text-blue-700',
    in_progress: 'bg-amber-100 text-amber-700',
    completed: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
  };
  
  return (
    <span className={cn(
      "rounded px-1.5 py-0.5 text-xs font-medium",
      styles[status] || 'bg-gray-100 text-gray-700'
    )}>
      {status}
    </span>
  );
}

/**
 * Compact version for inline display in chat
 */
export function AgentActivityInline({ activities = [], showInChat = true }) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  
  if (!showInChat || activities.length === 0) {
    return null;
  }

  const latestActivity = activities[activities.length - 1];
  
  return (
    <div className="my-2 rounded-md border border-amber-200 bg-amber-50 p-2">
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="flex w-full items-center justify-between text-xs text-amber-800"
      >
        <div className="flex items-center gap-2">
          <span>{ACTIVITY_ICONS[latestActivity.activity_type] || '🤖'}</span>
          <span className="font-medium">
            {latestActivity.title}
          </span>
          {activities.length > 1 && (
            <span className="text-amber-600">
              (+{activities.length - 1} more)
            </span>
          )}
        </div>
        <span>{isCollapsed ? 'Show' : 'Hide'}</span>
      </button>
      
      {!isCollapsed && activities.length > 1 && (
        <div className="mt-2 pl-4 border-l border-amber-300 space-y-1">
          {activities.slice(0, -1).map((a, i) => (
            <div key={i} className="text-xs text-amber-700 flex items-center gap-2">
              <span>{ACTIVITY_ICONS[a.activity_type] || '📋'}</span>
              <span>{a.title}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Settings toggle component
 */
export function AgentActivityToggle({ enabled, onChange }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={enabled}
        onChange={(e) => onChange(e.target.checked)}
        className="rounded border-input"
      />
      <span>Show agent activity in chat</span>
    </label>
  );
}

export default AgentActivityPanel;
