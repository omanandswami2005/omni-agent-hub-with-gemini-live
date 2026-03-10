/**
 * GenUI: GenUIRenderer — Dynamic renderer for server-pushed UI components.
 */

import { lazy, Suspense } from 'react';
import LoadingSpinner from '@/components/shared/LoadingSpinner';

const components = {
  chart: lazy(() => import('@/components/genui/DynamicChart')),
  table: lazy(() => import('@/components/genui/DataTable')),
  card: lazy(() => import('@/components/genui/InfoCard')),
  code: lazy(() => import('@/components/genui/CodeBlock')),
  image: lazy(() => import('@/components/genui/ImageGallery')),
  timeline: lazy(() => import('@/components/genui/TimelineView')),
  markdown: lazy(() => import('@/components/genui/MarkdownRenderer')),
  diff: lazy(() => import('@/components/genui/DiffViewer')),
  weather: lazy(() => import('@/components/genui/WeatherWidget')),
  map: lazy(() => import('@/components/genui/MapView')),
};

export default function GenUIRenderer({ type, data }) {
  const Component = components[type];

  if (!Component) {
    // Fallback: treat as markdown if there's a content string, otherwise show raw JSON
    const Md = components.markdown;
    if (data?.content) {
      return (
        <Suspense fallback={<LoadingSpinner />}>
          <Md content={data.content} />
        </Suspense>
      );
    }
    return (
      <div className="rounded-lg border border-border p-4">
        <p className="text-xs text-muted-foreground">Unknown UI type: {type}</p>
        <pre className="mt-2 overflow-x-auto text-sm">{JSON.stringify(data, null, 2)}</pre>
      </div>
    );
  }

  return (
    <Suspense fallback={<LoadingSpinner />}>
      <Component {...data} />
    </Suspense>
  );
}
