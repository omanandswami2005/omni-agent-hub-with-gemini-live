/**
 * Shared: ErrorBoundary — React error boundary.
 */

import { Component } from 'react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center p-8 text-center">
          <h2 className="text-lg font-medium">Something went wrong</h2>
          <p className="mt-2 text-sm text-muted-foreground">{this.state.error?.message}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground"
          >
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
