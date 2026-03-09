/**
 * GenUI: WeatherWidget — Weather information display.
 */

export default function WeatherWidget({ location = '', temp, condition, icon }) {
  return (
    <div className="flex items-center gap-4 rounded-lg border border-border p-4">
      <span className="text-4xl">{icon || '🌤️'}</span>
      <div>
        <p className="font-medium">{location}</p>
        <p className="text-2xl font-bold">{temp}°</p>
        <p className="text-sm text-muted-foreground">{condition}</p>
      </div>
    </div>
  );
}
