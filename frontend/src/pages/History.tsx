import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../auth/apiFetch';

interface Task {
  task_id: string;
  filename: string;
  provider: string;
  status: string;
  pii_masked: number;
  created_at: string;
}

function History() {
  const { data, isLoading } = useQuery<{ tasks: Task[] }>({
    queryKey: ['tasks'],
    queryFn: async () => {
      const res = await apiFetch('/api/tasks');
      if (!res.ok) throw new Error('Failed to fetch tasks');
      return res.json();
    },
  });

  const providerLabel = (id: string) => {
    switch (id) {
      case 'claude': return 'Claude';
      case 'openai': return 'GPT-4.1';
      case 'gemini': return 'Gemini 2.5 Flash';
      default: return id;
    }
  };

  const statusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <span className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider bg-pp-accent/20 text-pp-accent border border-pp-accent/30 rounded-full">Completed</span>;
      case 'processing':
        return <span className="px-2.5 py-1 text-xs font-medium bg-yellow-900/40 text-yellow-400 rounded-full">Processing</span>;
      case 'failed':
        return <span className="px-2.5 py-1 text-xs font-medium bg-red-900/40 text-red-400 rounded-full">Error</span>;
      default:
        return <span className="px-2.5 py-1 text-xs font-medium bg-gray-700 text-gray-400 rounded-full">{status}</span>;
    }
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const handleDownload = async (taskId: string, filename: string) => {
    try {
      const res = await apiFetch(`/api/task/${taskId}/download`);
      if (!res.ok) throw new Error('Download failed');
      
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `result_${filename}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download failed:', err);
    }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <h2 className="text-2xl font-semibold text-white mb-8">Task History</h2>

      {isLoading ? (
        <div className="flex items-center gap-2 text-pp-text-muted py-8 justify-center">
          <div className="w-4 h-4 border-2 border-pp-accent border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">Loading...</span>
        </div>
      ) : !data?.tasks?.length ? (
        <div className="text-center py-16">
          <p className="text-pp-text-muted text-sm">No tasks found</p>
          <p className="text-pp-text-muted/50 text-xs mt-1">New tasks will appear here after processing</p>
        </div>
      ) : (
        <div className="bg-pp-surface border border-pp-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-pp-border">
                <th className="text-left px-5 py-3.5 text-xs font-semibold text-pp-text-muted uppercase tracking-wider">Date</th>
                <th className="text-left px-5 py-3.5 text-xs font-semibold text-pp-text-muted uppercase tracking-wider">File</th>
                <th className="text-left px-5 py-3.5 text-xs font-semibold text-pp-text-muted uppercase tracking-wider">Provider</th>
                <th className="text-center px-5 py-3.5 text-xs font-semibold text-pp-text-muted uppercase tracking-wider">Masked</th>
                <th className="text-center px-5 py-3.5 text-xs font-semibold text-pp-text-muted uppercase tracking-wider">Status</th>
                <th className="text-right px-5 py-3.5 text-xs font-semibold text-pp-text-muted uppercase tracking-wider">Action</th>
              </tr>
            </thead>
            <tbody>
              {data.tasks.map((task) => (
                <tr key={task.task_id} className="border-b border-pp-border/50 hover:bg-pp-surface-light transition-colors">
                  <td className="px-5 py-3.5 text-pp-text-muted">{formatDate(task.created_at)}</td>
                  <td className="px-5 py-3.5 text-white font-medium">{task.filename}</td>
                  <td className="px-5 py-3.5 text-pp-text">{providerLabel(task.provider)}</td>
                  <td className="px-5 py-3.5 text-center">
                    <span className="bg-pp-surface-light px-2.5 py-1 rounded-full text-xs font-medium">{task.pii_masked}</span>
                  </td>
                  <td className="px-5 py-3.5 text-center">{statusBadge(task.status)}</td>
                  <td className="px-5 py-3.5 text-right">
                    {task.status === 'completed' && (
                      <button
                        onClick={() => handleDownload(task.task_id, task.filename)}
                        className="text-xs font-bold uppercase tracking-widest text-pp-accent hover:text-pp-accent-light transition-colors"
                      >
                        Download ↓
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default History;
