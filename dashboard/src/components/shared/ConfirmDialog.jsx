/**
 * Shared: ConfirmDialog — Confirmation modal dialog.
 */

export default function ConfirmDialog({ open, title, message, onConfirm, onCancel }) {
    if (!open) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="w-full max-w-md rounded-lg border border-border bg-background p-6">
                <h3 className="text-lg font-medium">{title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{message}</p>
                <div className="mt-6 flex justify-end gap-2">
                    <button onClick={onCancel} className="rounded-lg border border-border px-4 py-2 text-sm">
                        Cancel
                    </button>
                    <button onClick={onConfirm} className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground">
                        Confirm
                    </button>
                </div>
            </div>
        </div>
    );
}
