/**
 * MCP: MCPIcon — Renders a brand icon for known MCP plugins.
 *
 * Maps icon string identifiers to Lucide icons or inline SVG paths.
 * Falls back to a coloured circle with the first letter.
 */

import {
    Search,
    Github,
    MessageSquare,
    Globe,
    FolderOpen,
    Terminal,
    HardDrive,
    Database,
    Calendar,
    Cloud,
    FileText,
    Map,
    Bot,
} from 'lucide-react';

const ICON_MAP = {
    brave: { Icon: Search, color: '#FB542B' },
    github: { Icon: Github, color: '#8B5CF6' },
    slack: { Icon: MessageSquare, color: '#E01E5A' },
    notion: { Icon: FileText, color: '#000000' },
    playwright: { Icon: Globe, color: '#2EAD33' },
    filesystem: { Icon: FolderOpen, color: '#F59E0B' },
    folder: { Icon: FolderOpen, color: '#F59E0B' },
    sandbox: { Icon: Terminal, color: '#10B981' },
    'e2b': { Icon: Terminal, color: '#10B981' },
    'google-drive': { Icon: HardDrive, color: '#4285F4' },
    'google-maps': { Icon: Map, color: '#34A853' },
    'google-calendar': { Icon: Calendar, color: '#4285F4' },
    'vertex-ai': { Icon: Bot, color: '#4285F4' },
    'cloud-sql': { Icon: Database, color: '#4285F4' },
    cloud: { Icon: Cloud, color: '#4285F4' },
};

const LETTER_COLORS = [
    '#EF4444', '#F59E0B', '#10B981', '#3B82F6',
    '#8B5CF6', '#EC4899', '#14B8A6', '#F97316',
];

function letterColor(name) {
    const code = (name || '?').charCodeAt(0);
    return LETTER_COLORS[code % LETTER_COLORS.length];
}

export default function MCPIcon({ icon, name, size = 28 }) {
    const entry = ICON_MAP[icon];

    if (entry) {
        const { Icon, color } = entry;
        return (
            <div
                className="flex shrink-0 items-center justify-center rounded-lg"
                style={{ width: size + 8, height: size + 8, backgroundColor: `${color}18` }}
            >
                <Icon size={size * 0.65} style={{ color }} strokeWidth={1.8} />
            </div>
        );
    }

    // Fallback: first letter in coloured circle
    const letter = (name || icon || '?')[0].toUpperCase();
    const bg = letterColor(name || icon);
    return (
        <div
            className="flex shrink-0 items-center justify-center rounded-lg text-white font-semibold"
            style={{ width: size + 8, height: size + 8, backgroundColor: bg, fontSize: size * 0.45 }}
        >
            {letter}
        </div>
    );
}
