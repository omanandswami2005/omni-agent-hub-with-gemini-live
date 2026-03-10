/**
 * Page: NotFoundPage — 404 page.
 */

import { Link } from 'react-router';

export default function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <h1 className="text-6xl font-bold">404</h1>
      <p className="mt-4 text-lg text-muted-foreground">Page not found</p>
      <Link to="/" className="mt-6 rounded-lg bg-primary px-6 py-2 text-sm text-primary-foreground">
        Go Home
      </Link>
    </div>
  );
}
