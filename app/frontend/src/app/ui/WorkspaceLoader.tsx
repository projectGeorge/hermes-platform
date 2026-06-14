type WorkspaceLoaderProps = {
  label?: string;
};

/**
 * Centered route-level loading indicator.
 * Use inside a content area for full-route pending states.
 * For pre-shell (Clerk auth check) use the bare spinner in ProtectedRoute.
 */
export function WorkspaceLoader({ label }: WorkspaceLoaderProps) {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-white/10 border-t-[var(--hermes-accent)]" />
        {label ? (
          <p className="text-sm text-[var(--hermes-muted)]">{label}</p>
        ) : null}
      </div>
    </div>
  );
}
