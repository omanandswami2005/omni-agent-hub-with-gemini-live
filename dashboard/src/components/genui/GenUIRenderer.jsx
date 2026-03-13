/**
 * GenUI: GenUIRenderer — Dynamic renderer using the pluggable GenUI registry.
 *
 * Renders any component registered via registerGenUI(). Developers add new
 * GenUI components by registering them in genui-builtins.js (or any other
 * file that calls registerGenUI). This renderer lazy-loads the component
 * on first use.
 *
 * Forward-compatible with OpenUI: when OpenUI is integrated, the <Renderer>
 * can replace this component, consuming the same registry entries.
 */

import { lazy, Suspense, useMemo } from 'react';
import LoadingSpinner from '@/components/shared/LoadingSpinner';
import { getGenUI } from '@/lib/genui-registry';

// Cache lazy-wrapped components so React.lazy is only called once per type
const _lazyCache = new Map();

function getLazyComponent(type) {
  if (_lazyCache.has(type)) return _lazyCache.get(type);
  const entry = getGenUI(type);
  if (!entry) return null;
  const LazyComp = lazy(entry.component);
  _lazyCache.set(type, LazyComp);
  return LazyComp;
}

export default function GenUIRenderer({ type, data }) {
  const Component = useMemo(() => getLazyComponent(type), [type]);
  const MdFallback = useMemo(() => getLazyComponent('markdown'), []);

  if (!Component) {
    // Unknown type — try markdown fallback for text content
    if (MdFallback && data?.content) {
      return (
        <Suspense fallback={<LoadingSpinner />}>
          <MdFallback content={data.content} />
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
