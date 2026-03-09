/**
 * Page: DashboardPage — Main dashboard with chat panel and activity overview.
 */

import ChatPanel from '@/components/chat/ChatPanel';

export default function DashboardPage() {
    return (
        <div className="flex h-full gap-4">
            <div className="flex-1">
                <ChatPanel />
            </div>
            <aside className="hidden w-80 space-y-4 overflow-y-auto lg:block">
                {/* Active persona card */}
                {/* Connected clients status */}
                {/* Recent tool calls */}
                {/* Sandbox preview */}
            </aside>
        </div>
    );
}
