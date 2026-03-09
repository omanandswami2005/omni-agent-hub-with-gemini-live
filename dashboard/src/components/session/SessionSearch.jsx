/**
 * Session: SessionSearch — Search/filter for sessions.
 */

export default function SessionSearch({ value = '', onChange }) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
      placeholder="Search sessions..."
      className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
    />
  );
}
