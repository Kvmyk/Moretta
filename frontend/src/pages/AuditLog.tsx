import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../auth/apiFetch';

interface AuditEntry {
  timestamp: string;
  event: string;
  session_id?: string;
  filename?: string;
  pii_count?: number;
  pii_types?: string[];
  provider?: string;
  data_left_boundary?: boolean;
  error?: string;
  [key: string]: unknown;
}

function AuditLog() {
  const [limit] = useState(100);
  const [offset, setOffset] = useState(0);

  const { data, isLoading } = useQuery<{ entries: AuditEntry[]; total: number }>({
    queryKey: ['audit', limit, offset],
    queryFn: async () => {
      const res = await apiFetch(`/api/audit?limit=${limit}&offset=${offset}`);
      if (!res.ok) throw new Error('Failed to fetch audit log');
      return res.json();
    },
  });

  const formatTimestamp = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const eventLabel = (event: string) => {
    const labels: Record<string, string> = {
      'file_uploaded': 'File uploaded',
      'pii_detected': 'PII detected',
      'task_created': 'Task created',
      'ai_response_received': 'AI Response',
      'reinjection_complete': 'Re-injection complete',
      'task_failed': 'Task failed',
    };
    return labels[event] || event;
  };

  const eventColor = (event: string) => {
    if (event.includes('failed')) return 'text-red-400';
    if (event.includes('uploaded') || event.includes('created')) return 'text-blue-400';
    if (event.includes('complete') || event.includes('received')) return 'text-green-400';
    return 'text-pp-text-muted';
  };

  const handleExportCSV = async () => {
    try {
      const res = await apiFetch('/api/audit?limit=10000&offset=0');
      const allData = await res.json();
      if (!allData.entries?.length) return;

      const entries = allData.entries as AuditEntry[];
      const keys = Object.keys(entries[0]);
      const csvLines: string[] = [keys.join(',')];

      for (const entry of entries) {
        const row = keys.map((k) => {
          const val = entry[k];
          const str = typeof val === 'object' ? JSON.stringify(val) : String(val ?? '');
          return str.includes(',') || str.includes('"') ? `"${str.replace(/"/g, '""')}"` : str;
        });
        csvLines.push(row.join(','));
      }

      const blob = new Blob([csvLines.join('\n')], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_log_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('CSV export failed:', err);
    }
  };

  const total = data?.total ?? 0;
  const canPrev = offset > 0;
  const canNext = offset + limit < total;

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-semibold text-white">Audit Logs</h2>
          <p className="text-sm text-pp-text-muted mt-1">
            Immutable log of all events — {total} entries
          </p>
        </div>
        <button
          onClick={handleExportCSV}
          className="px-4 py-2 bg-pp-surface border border-pp-border rounded-lg text-sm font-medium text-pp-text hover:bg-pp-surface-light transition-colors"
        >
          CSV Export ↓
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-pp-text-muted py-8 justify-center">
          <div className="w-4 h-4 border-2 border-pp-accent border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">Loading...</span>
        </div>
      ) : !data?.entries?.length ? (
        <div className="text-center py-16">
          <p className="text-pp-text-muted text-sm">No audit entries found</p>
        </div>
      ) : (
        <>
          <div className="bg-pp-surface border border-pp-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-pp-border">
                  <th className="text-left px-5 py-3.5 text-xs font-semibold text-pp-text-muted uppercase tracking-wider">Time</th>
                  <th className="text-left px-5 py-3.5 text-xs font-semibold text-pp-text-muted uppercase tracking-wider">Event</th>
                  <th className="text-left px-5 py-3.5 text-xs font-semibold text-pp-text-muted uppercase tracking-wider">Session</th>
                  <th className="text-left px-5 py-3.5 text-xs font-semibold text-pp-text-muted uppercase tracking-wider">File</th>
                  <th className="text-center px-5 py-3.5 text-xs font-semibold text-pp-text-muted uppercase tracking-wider">PII</th>
                  <th className="text-center px-5 py-3.5 text-xs font-semibold text-pp-text-muted uppercase tracking-wider">Boundary</th>
                </tr>
              </thead>
              <tbody>
                {data.entries.map((entry, i) => (
                  <tr key={i} className="border-b border-pp-border/50 hover:bg-pp-surface-light transition-colors">
                    <td className="px-5 py-3 text-pp-text-muted font-mono text-xs">{formatTimestamp(entry.timestamp)}</td>
                    <td className={`px-5 py-3 font-medium ${eventColor(entry.event)}`}>{eventLabel(entry.event)}</td>
                    <td className="px-5 py-3 text-pp-text-muted font-mono text-xs">{entry.session_id?.slice(0, 8) ?? '—'}</td>
                    <td className="px-5 py-3 text-pp-text">{entry.filename ?? '—'}</td>
                    <td className="px-5 py-3 text-center text-pp-text-muted">{entry.pii_count ?? '—'}</td>
                    <td className="px-5 py-3 text-center">
                      {entry.data_left_boundary === false ? (
                        <span className="text-green-400 text-xs font-medium">0 ✓</span>
                      ) : entry.data_left_boundary === true ? (
                        <span className="text-red-400 text-xs font-bold">⚠ ALERT</span>
                      ) : (
                        <span className="text-pp-text-muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between mt-4">
            <span className="text-xs text-pp-text-muted">
              Showing {offset + 1}–{Math.min(offset + limit, total)} of {total}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={!canPrev}
                className="px-3 py-1.5 text-xs bg-pp-surface border border-pp-border rounded-lg text-pp-text-muted disabled:opacity-30 hover:bg-pp-surface-light transition-colors"
              >
                ← Previous
              </button>
              <button
                onClick={() => setOffset(offset + limit)}
                disabled={!canNext}
                className="px-3 py-1.5 text-xs bg-pp-surface border border-pp-border rounded-lg text-pp-text-muted disabled:opacity-30 hover:bg-pp-surface-light transition-colors"
              >
                Next →
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default AuditLog;
