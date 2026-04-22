import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../auth/apiFetch';

interface Conversation {
  conversation_id: string;
  task_id: string;
  title: string;
  filename: string;
  provider: string;
  model: string;
  status: string;
  pii_masked: number;
  created_at: string;
  last_activity_at: string;
  message_count: number;
  last_message_preview: string;
  context_expired?: boolean;
}

function History() {
  const navigate = useNavigate();
  const [providerFilter, setProviderFilter] = useState('all');
  const [modelFilter, setModelFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  const { data, isLoading } = useQuery<{ conversations: Conversation[] }>({
    queryKey: ['conversations'],
    queryFn: async () => {
      const res = await apiFetch('/api/conversations');
      if (!res.ok) throw new Error('Failed to fetch conversations');
      return res.json();
    },
  });

  const conversations = data?.conversations ?? [];
  const providerOptions = Array.from(new Set(conversations.map((item) => item.provider).filter(Boolean))).sort();
  const modelOptions = Array.from(new Set(conversations.map((item) => item.model).filter(Boolean))).sort();

  const filteredConversations = conversations.filter((conversation) => {
    if (providerFilter !== 'all' && conversation.provider !== providerFilter) return false;
    if (modelFilter !== 'all' && conversation.model !== modelFilter) return false;
    if (statusFilter !== 'all' && conversation.status !== statusFilter) return false;
    return true;
  });

  const providerLabel = (id: string) => {
    switch (id) {
      case 'claude': return 'Claude';
      case 'openai': return 'OpenAI';
      case 'gemini': return 'Gemini';
      case 'openrouter': return 'OpenRouter';
      case 'ollama': return 'Ollama';
      default: return id || 'Unknown';
    }
  };

  const statusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <span className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider bg-pp-accent/20 text-pp-accent border border-pp-accent/30 rounded-full">Completed</span>;
      case 'processing':
        return <span className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider bg-yellow-900/40 text-yellow-400 border border-yellow-700/40 rounded-full">Processing</span>;
      case 'failed':
        return <span className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider bg-red-900/40 text-red-400 border border-red-700/40 rounded-full">Failed</span>;
      default:
        return <span className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider bg-pp-border/60 text-pp-text-muted rounded-full">{status}</span>;
    }
  };

  const formatDate = (iso: string) => {
    if (!iso) return '-';
    const date = new Date(iso);
    return date.toLocaleDateString('en-US', {
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
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `result_${filename}`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Download failed:', error);
    }
  };

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex items-end justify-between gap-6 mb-8 flex-wrap">
        <div>
          <h2 className="text-2xl font-semibold text-white">Conversation History</h2>
          <p className="text-sm text-pp-text-muted mt-2">Each thread is scoped to the authenticated user and keeps provider/model metadata per conversation.</p>
        </div>

        <div className="flex gap-3 flex-wrap">
          <select
            value={providerFilter}
            onChange={(event) => setProviderFilter(event.target.value)}
            className="bg-pp-surface border border-pp-border rounded-lg px-3 py-2 text-sm text-white"
          >
            <option value="all">All providers</option>
            {providerOptions.map((provider) => (
              <option key={provider} value={provider}>{providerLabel(provider)}</option>
            ))}
          </select>

          <select
            value={modelFilter}
            onChange={(event) => setModelFilter(event.target.value)}
            className="bg-pp-surface border border-pp-border rounded-lg px-3 py-2 text-sm text-white"
          >
            <option value="all">All models</option>
            {modelOptions.map((model) => (
              <option key={model} value={model}>{model}</option>
            ))}
          </select>

          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="bg-pp-surface border border-pp-border rounded-lg px-3 py-2 text-sm text-white"
          >
            <option value="all">All statuses</option>
            <option value="completed">Completed</option>
            <option value="processing">Processing</option>
            <option value="failed">Failed</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-pp-text-muted py-8 justify-center">
          <div className="w-4 h-4 border-2 border-pp-accent border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">Loading...</span>
        </div>
      ) : !filteredConversations.length ? (
        <div className="text-center py-16 bg-pp-surface border border-pp-border rounded-2xl">
          <p className="text-pp-text-muted text-sm">No conversations found</p>
          <p className="text-pp-text-muted/50 text-xs mt-1">Your conversations will appear here after you create a task.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredConversations.map((conversation) => (
            <div
              key={conversation.conversation_id}
              className="bg-pp-surface border border-pp-border rounded-2xl p-5 shadow-sm"
            >
              <div className="flex items-start justify-between gap-6 flex-wrap">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-3 flex-wrap mb-2">
                    <h3 className="text-white font-semibold text-lg truncate">{conversation.title}</h3>
                    {statusBadge(conversation.status)}
                  </div>

                  <div className="flex gap-2 flex-wrap mb-3">
                    <span className="px-2.5 py-1 rounded-full bg-pp-bg border border-pp-border text-xs text-pp-text">{providerLabel(conversation.provider)}</span>
                    <span className="px-2.5 py-1 rounded-full bg-pp-bg border border-pp-border text-xs text-pp-text font-mono">{conversation.model || 'default-model'}</span>
                    <span className="px-2.5 py-1 rounded-full bg-pp-bg border border-pp-border text-xs text-pp-text-muted">{conversation.message_count} messages</span>
                    <span className="px-2.5 py-1 rounded-full bg-pp-bg border border-pp-border text-xs text-pp-text-muted">{conversation.pii_masked} masked</span>
                    {conversation.context_expired && (
                      <span className="px-2.5 py-1 rounded-full bg-yellow-900/30 border border-yellow-700/40 text-xs text-yellow-300">Context expired</span>
                    )}
                  </div>

                  <p className="text-sm text-pp-text">{conversation.filename}</p>
                  {conversation.last_message_preview && (
                    <p className="text-sm text-pp-text-muted mt-2 line-clamp-2">{conversation.last_message_preview}</p>
                  )}
                </div>

                <div className="flex flex-col items-end gap-3 shrink-0">
                  <div className="text-right">
                    <p className="text-xs uppercase tracking-widest text-pp-text-muted">Last activity</p>
                    <p className="text-sm text-white mt-1">{formatDate(conversation.last_activity_at)}</p>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => navigate(`/?conversation=${conversation.conversation_id}`)}
                      className="px-4 py-2 rounded-lg bg-pp-accent text-pp-bg text-xs font-bold uppercase tracking-widest hover:bg-pp-accent-light transition-colors"
                    >
                      Open
                    </button>
                    {conversation.status === 'completed' && (
                      <button
                        onClick={() => handleDownload(conversation.task_id, conversation.filename)}
                        className="px-4 py-2 rounded-lg border border-pp-border text-xs font-bold uppercase tracking-widest text-pp-text hover:bg-pp-bg transition-colors"
                      >
                        Download
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default History;
