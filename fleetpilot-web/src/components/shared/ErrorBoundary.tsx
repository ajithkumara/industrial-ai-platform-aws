import * as React from "react";

/** Shows what went wrong instead of a blank page. Resets when `resetKey` (the route) changes. */
export class ErrorBoundary extends React.Component<{ resetKey: string; children: React.ReactNode }, { error?: Error }> {
  state: { error?: Error } = {};
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidUpdate(prev: { resetKey: string }) { if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: undefined }); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto mt-16 max-w-md rounded-lg border bg-card p-6 text-sm">
        <div className="text-base font-semibold">This page hit a problem</div>
        <p className="mt-1 text-muted-foreground">The rest of FleetPilot still works. Go back or pick another page.</p>
        <pre className="mt-3 overflow-auto rounded bg-muted p-2 text-xs">{this.state.error.message}</pre>
      </div>
    );
  }
}
