/**
 * GenUI: MapView — Map display for location results.
 */

// TODO: Implement with Google Maps embed or Leaflet

export default function MapView({ lat, lng, zoom = 13, markers = [] }) {
  return (
    <div className="h-64 w-full rounded-lg border border-border bg-muted">
      <p className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Map: {lat}, {lng} (zoom {zoom}) — {markers.length} markers
      </p>
    </div>
  );
}
