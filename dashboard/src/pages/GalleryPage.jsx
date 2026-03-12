/**
 * Page: GalleryPage — Grid view of all AI-generated images stored in GCS.
 * Fetches signed URLs from /api/v1/gallery, supports pagination & lightbox.
 */

import { useEffect, useState, useCallback } from 'react';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { api } from '@/lib/api';
import { Image as ImageIcon, Loader2, X, Download, ChevronLeft, ChevronRight } from 'lucide-react';

export default function GalleryPage() {
    useDocumentTitle('Gallery');
    const [images, setImages] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [page, setPage] = useState(1);
    const [hasMore, setHasMore] = useState(false);
    const [total, setTotal] = useState(0);
    const [lightbox, setLightbox] = useState(null); // index into images array

    const fetchImages = useCallback(async (p) => {
        setLoading(true);
        setError(null);
        try {
            const res = await api.get(`/gallery?page=${p}&limit=50`);
            if (p === 1) {
                setImages(res.images);
            } else {
                setImages((prev) => [...prev, ...res.images]);
            }
            setTotal(res.total);
            setHasMore(res.has_more);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchImages(1);
    }, [fetchImages]);

    const loadMore = () => {
        const next = page + 1;
        setPage(next);
        fetchImages(next);
    };

    const openLightbox = (index) => setLightbox(index);
    const closeLightbox = () => setLightbox(null);
    const prevImage = () => setLightbox((i) => (i > 0 ? i - 1 : i));
    const nextImage = () => setLightbox((i) => (i < images.length - 1 ? i + 1 : i));

    // Keyboard navigation for lightbox
    useEffect(() => {
        if (lightbox === null) return;
        const handler = (e) => {
            if (e.key === 'Escape') closeLightbox();
            if (e.key === 'ArrowLeft') prevImage();
            if (e.key === 'ArrowRight') nextImage();
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    });

    return (
        <div className="space-y-6 p-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold">Image Gallery</h1>
                    <p className="text-sm text-muted-foreground">
                        {total > 0 ? `${total} images generated across all sessions` : 'AI-generated images from your sessions'}
                    </p>
                </div>
            </div>

            {/* Error state */}
            {error && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
                    {error}
                </div>
            )}

            {/* Empty state */}
            {!loading && !error && images.length === 0 && (
                <div className="flex h-[50vh] flex-col items-center justify-center gap-3 text-muted-foreground">
                    <div className="rounded-full bg-muted/50 p-6">
                        <ImageIcon size={32} />
                    </div>
                    <p className="text-lg font-medium">No images yet</p>
                    <p className="text-sm">Generated images will appear here automatically</p>
                </div>
            )}

            {/* Image grid */}
            {images.length > 0 && (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
                    {images.map((img, index) => (
                        <button
                            key={img.gcs_path}
                            onClick={() => openLightbox(index)}
                            className="group relative aspect-square overflow-hidden rounded-lg border border-border/50 bg-muted/20 transition-all hover:border-border hover:shadow-md focus:outline-none focus:ring-2 focus:ring-primary/50"
                        >
                            <img
                                src={img.url}
                                alt={img.filename}
                                className="h-full w-full object-cover transition-transform group-hover:scale-105"
                                loading="lazy"
                            />
                            <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
                            <p className="absolute bottom-0 left-0 right-0 truncate px-2 py-1.5 text-[10px] text-white opacity-0 transition-opacity group-hover:opacity-100">
                                {img.filename}
                            </p>
                        </button>
                    ))}
                </div>
            )}

            {/* Load more */}
            {hasMore && (
                <div className="flex justify-center pt-4">
                    <button
                        onClick={loadMore}
                        disabled={loading}
                        className="rounded-lg border border-border px-6 py-2 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
                    >
                        {loading ? <Loader2 size={16} className="animate-spin" /> : 'Load More'}
                    </button>
                </div>
            )}

            {/* Initial loading */}
            {loading && images.length === 0 && (
                <div className="flex h-[50vh] items-center justify-center">
                    <Loader2 size={32} className="animate-spin text-muted-foreground" />
                </div>
            )}

            {/* Lightbox overlay */}
            {lightbox !== null && images[lightbox] && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
                    onClick={closeLightbox}
                >
                    {/* Close */}
                    <button
                        onClick={closeLightbox}
                        className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
                    >
                        <X size={20} />
                    </button>

                    {/* Navigation */}
                    {lightbox > 0 && (
                        <button
                            onClick={(e) => { e.stopPropagation(); prevImage(); }}
                            className="absolute left-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
                        >
                            <ChevronLeft size={24} />
                        </button>
                    )}
                    {lightbox < images.length - 1 && (
                        <button
                            onClick={(e) => { e.stopPropagation(); nextImage(); }}
                            className="absolute right-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20 top-1/2 -translate-y-1/2"
                        >
                            <ChevronRight size={24} />
                        </button>
                    )}

                    {/* Image */}
                    <img
                        src={images[lightbox].url}
                        alt={images[lightbox].filename}
                        className="max-h-[85vh] max-w-[90vw] rounded-lg object-contain shadow-2xl"
                        onClick={(e) => e.stopPropagation()}
                    />

                    {/* Footer info */}
                    <div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-3 rounded-full bg-black/60 px-4 py-2 text-sm text-white">
                        <span>{images[lightbox].filename}</span>
                        <span className="text-white/50">•</span>
                        <span className="text-white/70">{lightbox + 1} / {images.length}</span>
                        <a
                            href={images[lightbox].url}
                            download={images[lightbox].filename}
                            onClick={(e) => e.stopPropagation()}
                            className="ml-2 rounded-full bg-white/10 p-1.5 hover:bg-white/20"
                            title="Download"
                        >
                            <Download size={14} />
                        </a>
                    </div>
                </div>
            )}
        </div>
    );
}
