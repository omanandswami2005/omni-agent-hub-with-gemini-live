/**
 * GenUI: ImageGallery — Display generated or fetched images.
 */

export default function ImageGallery({ images = [], caption = '' }) {
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        {images.map((img, i) => (
          <img
            key={i}
            src={img.url || img}
            alt={img.alt || `Image ${i + 1}`}
            className="rounded-lg object-cover"
            loading="lazy"
          />
        ))}
      </div>
      {caption && <p className="text-sm text-muted-foreground">{caption}</p>}
    </div>
  );
}
