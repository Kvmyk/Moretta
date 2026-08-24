interface AdminOnlyNoticeProps {
  resource: string;
}

/**
 * Shown when the API rejects an instance-wide view for lack of an admin role.
 * The audit log and dashboard aggregate every user's activity, so they are
 * gated server-side; this explains the 403 instead of showing a generic error.
 */
function AdminOnlyNotice({ resource }: AdminOnlyNoticeProps) {
  return (
    <div className="flex items-center justify-center h-full p-8">
      <div className="max-w-md text-center">
        <div className="mx-auto mb-4 w-12 h-12 rounded-full bg-pp-surface border border-pp-border flex items-center justify-center">
          <svg
            className="w-6 h-6 text-pp-text-muted"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-pp-text mb-2">Administrator access required</h2>
        <p className="text-sm text-pp-text-muted">
          The {resource} covers activity across every user of this instance. Ask an
          administrator to grant your account the required role in Keycloak.
        </p>
      </div>
    </div>
  );
}

export default AdminOnlyNotice;
