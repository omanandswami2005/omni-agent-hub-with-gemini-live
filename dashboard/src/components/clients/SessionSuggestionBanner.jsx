import { useState } from 'react';
import { Monitor, Smartphone, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useSessionSuggestionStore } from '@/stores/sessionSuggestionStore';

const clientIcons = {
    desktop: Monitor,
    mobile: Smartphone,
    web: Monitor,
};

export default function SessionSuggestionBanner() {
    const { suggestion, dismiss, enableAutoJoin } = useSessionSuggestionStore();
    const [alwaysJoin, setAlwaysJoin] = useState(false);

    if (!suggestion) return null;

    const handleDismiss = () => {
        if (alwaysJoin) enableAutoJoin();
        dismiss();
    };

    const devices = suggestion.availableClients || [];

    return (
        <div className="fixed top-4 left-1/2 z-50 -translate-x-1/2 w-full max-w-md animate-in slide-in-from-top-4 fade-in duration-300">
            <div className="rounded-lg border border-border bg-card shadow-lg p-4">
                <div className="flex items-start gap-3">
                    <div className="flex shrink-0 items-center gap-1 pt-0.5 text-muted-foreground">
                        {devices.map((d) => {
                            const Icon = clientIcons[d] || Monitor;
                            return <Icon key={d} className="h-5 w-5" />;
                        })}
                    </div>
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground">
                            Active session on {devices.join(', ')}
                        </p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                            You've been joined to your existing session for continuity.
                        </p>
                        <label className="flex items-center gap-2 mt-3 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={alwaysJoin}
                                onChange={(e) => setAlwaysJoin(e.target.checked)}
                                className="h-3.5 w-3.5 rounded border-border accent-primary"
                            />
                            <span className="text-xs text-muted-foreground">Always auto-join (don&apos;t show this again)</span>
                        </label>
                    </div>
                    <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={handleDismiss}>
                        <X className="h-4 w-4" />
                    </Button>
                </div>
            </div>
        </div>
    );
}
