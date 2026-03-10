/**
 * GenUI: MapView — Map display using Google Maps embed.
 */

export default function MapView({ lat, lng, zoom = 13, markers = [] }) {
  // Use the first marker or the provided lat/lng as center
  const centerLat = markers[0]?.lat ?? lat;
  const centerLng = markers[0]?.lng ?? lng;

  if (centerLat == null || centerLng == null) {
    return (
      <div className="flex h-64 w-full items-center justify-center rounded-lg border border-border bg-muted text-sm text-muted-foreground">
        No location data
      </div>
    );
  }

  const src = `https://www.google.com/maps/embed/v1/view?key=${import.meta.env.VITE_GOOGLE_MAPS_KEY || ''}&center=${centerLat},${centerLng}&zoom=${zoom}`;

  return (
    <div className="h-64 w-full overflow-hidden rounded-lg border border-border">
      <iframe
        title="Map view"
        src={src}
        className="h-full w-full border-0"
        allowFullScreen
        loading="lazy"
        referrerPolicy="no-referrer-when-downgrade"
      />
    </div>
  );
}
