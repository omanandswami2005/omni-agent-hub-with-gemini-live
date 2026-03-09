/**
 * Shared: StatusDot — Colored status indicator dot.
 */

const STATUS_COLORS = {
  online: 'bg-green-500',
  offline: 'bg-muted-foreground',
  busy: 'bg-yellow-500',
  error: 'bg-red-500',
};

export default function StatusDot({ status = 'offline', size = 'sm', pulse = false }) {
  const sizes = { sm: 'h-2 w-2', md: 'h-3 w-3', lg: 'h-4 w-4' };

  return (
    <span
      className={`inline-block rounded-full ${sizes[size]} ${STATUS_COLORS[status] || STATUS_COLORS.offline} ${
        pulse ? 'animate-pulse' : ''
      }`}
    />
  );
}
