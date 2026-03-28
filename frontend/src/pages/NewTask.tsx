import { useState, useCallback, useRef, useEffect } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import PiiDetectionCard from '../auth/components/PiiDetectionCard';
import ProviderSelector from '../auth/components/ProviderSelector';
import { apiFetch } from '../auth/apiFetch';

interface PiiType {
  type: string;
  label: string;
  count: number;
  severity: 'critical' | 'warning' | 'info';
  matches?: string[];
}

interface UploadResult {
  file_id: string;
  filename: string;
  size_bytes: number;
}

interface PiiResult {
  file_id: string;
  filename: string;
  total_pii: number;
  deep_scan_completed?: boolean;
  types: PiiType[];
}

interface PreviewData {
  type: 'spreadsheet' | 'document' | 'email';
  text?: string;
  sheets?: { name: string; rows: string[][] }[];
}

interface PreviewResult {
  file_id: string;
  anonymized_text: string;
  preview_data: PreviewData;
  tokens_used: number;
}

interface TaskResult {
  task_id: string;
  status: string;
}

function NewTask() {
  const [fileId, setFileId] = useState<string | null>(null);
  const [filename, setFilename] = useState<string>('');
  
  // Chat steps state
  const [step, setStep] = useState<'input' | 'pii_detected' | 'processing' | 'done'>('input');
  
  const [chatInput, setChatInput] = useState('');
  const [inputText, setInputText] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  
  // AI Config
  const [instruction, setInstruction] = useState('');
  const [provider, setProvider] = useState('claude');
  const [model, setModel] = useState('claude-sonnet-4.6-20260217');
  
  // Task states
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);
  const [securityError, setSecurityError] = useState<string | null>(null);
  const [pendingChatMessage, setPendingChatMessage] = useState<string | null>(null);
  const [pendingInstruction, setPendingInstruction] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);

  const chatTextareaRef = useRef<HTMLTextAreaElement>(null);
  const inputTextareaRef = useRef<HTMLTextAreaElement>(null);

  const autoResize = (el: HTMLTextAreaElement | null) => {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 220) + 'px';
  };

  const chatEndRef = useRef<HTMLDivElement>(null);

  const handleFileAction = useCallback((file: File) => {
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    const allowed = ['.docx', '.xlsx', '.eml', '.msg', '.txt'];
    if (allowed.includes(ext)) {
      setSelectedFile(file);
      setStep('input');
      setFileId(null);
      setTaskId(null);
      setTaskStatus(null);
      setSecurityError(null);
      setInstruction('');
      setInputText('');
    }
  }, []);

  const onDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current++;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  }, []);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current--;
    if (dragCounter.current === 0) {
      setIsDragging(false);
    }
  }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current = 0;
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      handleFileAction(file);
    }
  }, [handleFileAction]);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };



  // Upload or submit text mutation
  const submitDataMutation = useMutation({
    mutationFn: async () => {
      if (selectedFile) {
        const formData = new FormData();
        formData.append('file', selectedFile);
        const res = await apiFetch('/api/upload', { method: 'POST', body: formData });
        if (!res.ok) throw new Error('Upload failed');
        return res.json() as Promise<UploadResult>;
      } else if (inputText.trim()) {
        const res = await apiFetch('/api/text', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: inputText }),
        });
        if (!res.ok) throw new Error('Text submission failed');
        return res.json() as Promise<UploadResult>;
      }
      throw new Error('No data provided');
    },
    onSuccess: (data) => {
      setFileId(data.file_id);
      setFilename(data.filename);
      setStep('pii_detected');
    },
  });

  // Fetch PII details
  const piiQuery = useQuery<PiiResult>({
    queryKey: ['pii', fileId],
    queryFn: async () => {
      const res = await apiFetch(`/api/file/${fileId}/pii`);
      if (!res.ok) throw new Error('Failed to fetch PII');
      return res.json();
    },
    enabled: !!fileId,
    refetchInterval: (query) => {
      // Poll every 3 seconds if we have data and deep scan is NOT completed
      return query.state.data?.deep_scan_completed !== false ? false : 3000;
    },
  });

  // Fetch preview for text inputs
  const previewQuery = useQuery<PreviewResult>({
    queryKey: ['preview', fileId],
    queryFn: async () => {
      const res = await apiFetch(`/api/file/${fileId}/preview`);
      if (!res.ok) throw new Error('Failed to fetch preview');
      return res.json();
    },
    enabled: !!fileId,
    refetchInterval: () => {
      return piiQuery.data?.deep_scan_completed !== false ? false : 3000;
    },
  });

  // Fetch final result returning chat messages
  const resultQuery = useQuery<{ task_id: string; status: string; filename: string; messages: Array<{role: string, content: string}>; has_solution?: boolean; result_preview?: any }>({
    queryKey: ['result', taskId],
    queryFn: async () => {
      const res = await apiFetch(`/api/task/${taskId}/result`);
      if (!res.ok) throw new Error('Result fetch failed');
      return res.json();
    },
    enabled: !!taskId && taskStatus === 'completed',
  });

  // Chat mutation for multi-turn
  const sendChatMutation = useMutation({
    mutationFn: async (chatInstruction: string) => {
      const res = await apiFetch(`/api/task/${taskId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction: chatInstruction }),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Chat failed');
      }
      return res.json();
    },
    onMutate: (chatInstruction) => {
      setPendingChatMessage(chatInstruction);
    },
    onSuccess: () => {
      setSecurityError(null);
      setTaskStatus('processing');
      setStep('processing');
      setChatInput('');
      pollTaskStatus(taskId!);
    },
    onError: (error: Error) => {
      setSecurityError(error.message);
      setPendingChatMessage(null);
    }
  });

  // Selective scrolling - only on step change or new message
  useEffect(() => {
    scrollToBottom();
  }, [step, resultQuery.data?.messages.length, pendingChatMessage]);

  // Create task
  const createTaskMutation = useMutation({
    mutationFn: async () => {
      const res = await apiFetch('/api/task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: fileId,
          instruction: instruction || 'Process this text and fix errors.',
          provider,
          model,
        }),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Task creation failed');
      }
      return res.json() as Promise<TaskResult>;
    },
    onMutate: () => {
      // Show the instruction immediately as a user bubble
      if (instruction.trim()) {
        setPendingInstruction(instruction);
      }
    },
    onSuccess: (data) => {
      setSecurityError(null);
      setTaskId(data.task_id);
      setTaskStatus('processing');
      setStep('processing');
      pollTaskStatus(data.task_id);
    },
    onError: (error: Error) => {
      setSecurityError(error.message);
      setPendingInstruction(null);
    }
  });

  // Poll task status
  const pollTaskStatus = useCallback(async (tid: string) => {
    const poll = async () => {
      try {
        const res = await apiFetch(`/api/task/${tid}/status`);
        const data = await res.json();
        setTaskStatus(data.status);
        if (data.status === 'processing') {
          setTimeout(poll, 2000);
        } else if (data.status === 'completed') {
          setStep('done');
          setPendingChatMessage(null);
          setPendingInstruction(null);
        } else {
          setStep('done'); // Even if failed
          setPendingChatMessage(null);
          setPendingInstruction(null);
        }
      } catch {
        setTaskStatus('failed');
        setStep('done');
        setPendingChatMessage(null);
        setPendingInstruction(null);
      }
    };
    poll();
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
  };

  const handleSubmitInitial = () => {
    if (inputText.trim() || selectedFile) {
      setStep('pii_detected'); // Move to next step immediately to show user bubble
      submitDataMutation.mutate();
    }
  };

  const handleSendToAI = () => {
    if (fileId) {
      createTaskMutation.mutate();
    }
  };

  const handleDownloadResult = async () => {
    if (!taskId) return;
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
      console.error('Failed to download result:', err);
    }
  };

  const handleReset = () => {
    setFileId(null);
    setFilename('');
    setStep('input');
    setInputText('');
    setSelectedFile(null);
    setInstruction('');
    setTaskId(null);
    setTaskStatus(null);
    setSecurityError(null);
    setChatInput('');
    setPendingInstruction(null);
    setPendingChatMessage(null);
    // Reset textarea heights
    if (chatTextareaRef.current) chatTextareaRef.current.style.height = '64px';
    if (inputTextareaRef.current) inputTextareaRef.current.style.height = '64px';
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    return `${Math.round(bytes / 1024)} KB`;
  };

  const renderRichPreview = (preview: PreviewResult) => {
    const data = preview.preview_data;
    if (!data || data.type === 'document' || data.type === 'email') {
      return (
        <div className="bg-pp-bg rounded-xl border border-pp-border/50 p-4 mt-4 max-h-[400px] overflow-y-auto">
          <h5 className="text-xs font-semibold text-pp-text-muted flex items-center gap-2 mb-2">
            PREVIEW OF TEXT SENT TO AI (ANONYMIZED)
          </h5>
          <div className="text-sm font-mono text-pp-text break-words whitespace-pre-wrap leading-relaxed">
            {renderHighlightedText(data?.text || preview.anonymized_text)}
          </div>
        </div>
      );
    }

    if (data.type === 'spreadsheet') {
      return (
        <div className="mt-4 space-y-4">
           <h5 className="text-xs font-semibold text-pp-text-muted flex items-center gap-2">
             SHEET VISUALIZATION (SENSITIVE DATA MASKED)
           </h5>
           <div className="overflow-x-auto border border-pp-border rounded-xl bg-pp-bg shadow-inner max-h-[400px] overflow-y-auto custom-scrollbar">
            {data.sheets?.map((sheet, sIdx) => (
              <div key={sIdx} className="mb-0 last:mb-0">
                <div className="bg-white/5 px-4 py-2 text-xs font-bold text-pp-accent border-b border-pp-border flex items-center gap-2 sticky top-0 z-10 backdrop-blur-md">
                   <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                     <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                   </svg>
                   {sheet.name}
                </div>
                <div className="min-w-full inline-block align-middle">
                  <table className="min-w-full text-xs text-left border-collapse table-fixed">
                    <thead>
                      <tr className="bg-white/5 font-bold text-pp-text-muted/50 border-b border-pp-border">
                        <th className="w-10 p-2 border-r border-pp-border text-center">#</th>
                        {sheet.rows[0]?.map((_, i) => (
                          <th key={i} className="p-2 border-r border-pp-border last:border-0 w-32 uppercase tracking-wider">{String.fromCharCode(65 + i)}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sheet.rows.map((row, rIdx) => (
                        <tr key={rIdx} className="border-b border-pp-border/50 last:border-0 hover:bg-pp-accent/5 transition-colors">
                          <td className="p-2 border-r border-pp-border bg-white/5 text-center font-mono text-[10px] text-pp-text-muted">{rIdx + 1}</td>
                          {row.map((cell, cIdx) => (
                            <td key={cIdx} className="p-2 border-r border-pp-border/50 last:border-0 align-top">
                              <span className="break-words line-clamp-3 hover:line-clamp-none transition-all">{renderHighlightedText(cell)}</span>
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        </div>
      );
    }
  };

  const renderHighlightedText = (text: string) => {
    const parts = text.split(/(\[[A-Z0-9_]+_[a-f0-9]+\])/g);
    return parts.map((part, idx) => {
      if (part.match(/^\[[A-Z0-9_]+_[a-f0-9]+\]$/)) {
        return (
          <span key={idx} className="text-pp-accent font-bold bg-pp-accent/10 border border-pp-accent/20 px-1 py-0.5 rounded italic">
            {part}
          </span>
        );
      }
      return <span key={idx}>{part}</span>;
    });
  };

  return (
    <div 
      className="flex flex-col h-[calc(100vh-2rem)] relative"
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {isDragging && (
        <div className="absolute inset-0 z-50 bg-pp-bg/90 backdrop-blur-md flex items-center justify-center animate-in fade-in duration-300 pointer-events-none">
          <div className="border border-pp-accent/30 rounded-[2rem] p-12 flex flex-col items-center gap-6 bg-pp-surface shadow-[0_0_50px_rgba(184,175,200,0.1)]">
            <div className="w-24 h-24 rounded-full bg-pp-accent/5 flex items-center justify-center text-pp-accent border border-pp-accent/20">
              <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
            <p className="text-2xl font-serif text-white tracking-widest uppercase italic">Revelare</p>
            <p className="text-pp-accent-light opacity-60 text-xs tracking-widest uppercase font-medium">Drop your secrets here</p>
          </div>
        </div>
      )}
      {/* Header */}
      <div className="flex items-center justify-between mb-6 px-8 py-4 bg-pp-surface rounded-xl border border-pp-border shadow-2xl shadow-pp-accent/5 backdrop-blur-xl">
        <div>
          <h2 className="text-xl font-semibold text-white">Your Chat</h2>
          <p className="text-xs text-pp-accent mt-1 tracking-wider uppercase font-medium">Your data stays yours • Automatic PII Anonymization</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-pp-text-muted">AI Config:</span>
          <ProviderSelector
            provider={provider}
            model={model}
            onProviderChange={setProvider}
            onModelChange={setModel}
          />
          {step !== 'input' && (
            <button
              onClick={handleReset}
              className="ml-4 px-3 py-1.5 bg-pp-bg hover:bg-pp-border text-pp-text text-sm rounded-lg transition"
            >
              Start new
            </button>
          )}
        </div>
      </div>

      {/* Chat Messages Area */}
      <div className="flex-1 overflow-y-auto px-8 pb-32 space-y-8 scroll-smooth">
        
        {/* Intro bubble */}
        {step === 'input' && (
          <div className="flex gap-4">
            <div className="w-10 h-10 rounded-full bg-pp-accent shadow-lg shadow-pp-accent/20 flex items-center justify-center shrink-0">
               <svg className="w-6 h-6 text-pp-bg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div className="bg-pp-surface border border-pp-border rounded-2xl rounded-tl-sm p-5 max-w-2xl shadow-xl">
              <p className="text-sm text-pp-text leading-relaxed">
                Welcome to Moretta. Upload a document or type text — I will automatically anonymize sensitive data before processing it with your chosen AI models.
              </p>
            </div>
          </div>
        )}

        {/* User Message Bubble */}
        {step !== 'input' && (
          <div className="flex gap-4 flex-row-reverse">
            <div className="w-8 h-8 rounded-full bg-pp-bg border border-pp-border flex items-center justify-center shrink-0">
              <svg className="w-4 h-4 text-pp-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
            <div className="bg-pp-accent text-pp-bg rounded-2xl rounded-tr-sm p-4 max-w-2xl shadow-lg font-medium">
              {selectedFile ? (
                <div className="flex items-center gap-3">
                  <svg className="w-6 h-6 text-pp-bg/70" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                  </svg>
                  <div>
                    <span className="font-bold block">{selectedFile.name}</span>
                    <span className="text-xs text-pp-bg/70">{formatFileSize(selectedFile.size)}</span>
                  </div>
                </div>
              ) : (
                <p className="text-sm break-words whitespace-pre-wrap">{inputText}</p>
              )}
            </div>
          </div>
        )}

        {/* PII Detection Bubble */}
        {(step === 'pii_detected' || step === 'processing' || step === 'done') && (
          <div className="flex gap-4 animate-in fade-in slide-in-from-bottom-4">
            <div className="w-8 h-8 rounded-full bg-pp-accent flex items-center justify-center shrink-0">
               <svg className="w-4 h-4 text-pp-bg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div className="max-w-2xl w-full">
              {(piiQuery.isLoading || submitDataMutation.isPending) ? (
                <div className="bg-pp-surface border border-pp-border rounded-2xl rounded-tl-sm p-4">
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 border-2 border-pp-accent border-t-transparent rounded-full animate-spin" />
                    <span className="text-sm text-pp-text-muted">Analyzing text for sensitive data...</span>
                  </div>
                </div>
              ) : piiQuery.data ? (
                <div className="space-y-4">
                  <div className="bg-pp-surface border border-pp-border rounded-2xl rounded-tl-sm p-4 shadow-sm">
                    <p className="text-sm text-pp-text mb-4">
                      {piiQuery.data.deep_scan_completed === false 
                        ? 'Performing initial scan. I will launch deep analysis (Ollama) in a moment, wait for results before sending to AI.'
                        : `Scan complete. Found ${piiQuery.data.total_pii} sensitive fragments that have been safely anonymized.`}
                    </p>
                    <div className="bg-pp-bg rounded-xl border border-pp-border/50 p-3">
                      <PiiDetectionCard types={piiQuery.data.types} />
                    </div>

                    {previewQuery.data && renderRichPreview(previewQuery.data)}

                    {piiQuery.data.deep_scan_completed === false && (
                      <div className="flex items-center gap-3 mt-4 text-pp-text-muted bg-pp-bg/50 px-4 py-2 rounded-lg border border-pp-border/50">
                        <div className="w-3 h-3 border-2 border-pp-accent border-t-transparent rounded-full animate-spin" />
                        <span className="text-xs font-medium">Deep scan in progress (local LLM)...</span>
                      </div>
                    )}
                  </div>

                  {step === 'pii_detected' && (
                    <div className="bg-pp-surface border border-pp-border rounded-2xl p-4 shadow-sm animate-in fade-in">
                      <label className="block text-sm font-medium text-pp-text mb-2">
                        AI Instruction
                      </label>
                      <textarea
                        value={instruction}
                        onChange={(e) => setInstruction(e.target.value)}
                        disabled={piiQuery.data.deep_scan_completed === false}
                        placeholder={piiQuery.data.deep_scan_completed === false ? "Wait for scan to complete..." : "Write AI instruction..."}
                        className="w-full h-24 bg-pp-bg border border-pp-border rounded-xl px-4 py-3 text-sm text-white placeholder-pp-text-muted/50 resize-none focus:outline-none focus:border-pp-accent transition-colors mb-4 disabled:opacity-50"
                      />
                      <div className="flex justify-end">
                        <button
                          onClick={handleSendToAI}
                          disabled={createTaskMutation.isPending || piiQuery.data.deep_scan_completed === false}
                          className="px-6 py-2.5 bg-pp-accent hover:bg-pp-accent-light text-pp-bg text-sm font-bold rounded-xl transition-all shadow-md shadow-pp-accent/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                          {createTaskMutation.isPending ? 'Sending...' : 'Send to AI'}
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                          </svg>
                        </button>
                      </div>

                      {securityError && (
                        <div className="mt-4 p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex gap-3 items-start">
                          <svg className="w-5 h-5 text-red-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                          </svg>
                          <p className="text-sm text-red-400">{securityError}</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="bg-pp-surface border border-red-900/50 rounded-2xl rounded-tl-sm p-4 text-sm text-red-500">
                  An error occurred during analysis.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Chat Thread Messages */}
        {resultQuery.data?.messages.map((msg, idx) => {
          const hasSolution = resultQuery.data?.has_solution;
          const resultPreview = resultQuery.data?.result_preview;
          // Show result card for the latest assistant message when a solution exists
          const isLastAssistant = msg.role === 'assistant' && 
            idx === resultQuery.data!.messages.length - 1 && 
            hasSolution;

          return (
            <div key={idx} className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''} animate-in fade-in slide-in-from-bottom-2`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                msg.role === 'user' ? 'bg-pp-bg border border-pp-border' : 'bg-pp-accent'
              }`}>
                 {msg.role === 'user' ? (
                   <svg className="w-4 h-4 text-pp-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                     <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                   </svg>
                 ) : (
                   <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                     <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.989-2.386l-.548-.547z" />
                   </svg>
                 )}
              </div>
              <div className={`rounded-2xl p-4 max-w-2xl shadow-sm ${
                msg.role === 'user' ? 'bg-pp-accent rounded-tr-sm text-pp-bg font-medium' : 'bg-pp-surface border border-pp-border rounded-tl-sm text-pp-text'
              }`}>
                {isLastAssistant ? (
                  <div className="space-y-4">
                    {/* Chat message from AI */}
                    <p className="text-sm break-words whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                    
                    {/* Result Preview */}
                    {resultPreview && (
                      <div className="border-t border-pp-border pt-4">
                        <h5 className="text-xs font-semibold text-pp-accent flex items-center gap-2 mb-3 uppercase tracking-widest">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                          </svg>
                          Result Preview
                        </h5>
                        {resultPreview.type === 'spreadsheet' && resultPreview.sheets ? (
                          <div className="overflow-x-auto border border-pp-border rounded-xl bg-pp-bg shadow-inner max-h-[300px] overflow-y-auto custom-scrollbar">
                            {resultPreview.sheets.map((sheet: any, sIdx: number) => (
                              <div key={sIdx} className="mb-0 last:mb-0">
                                <div className="bg-white/5 px-4 py-2 text-xs font-bold text-pp-accent border-b border-pp-border flex items-center gap-2 sticky top-0 z-10 backdrop-blur-md">
                                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                  </svg>
                                  {sheet.name}
                                </div>
                                <div className="min-w-full inline-block align-middle">
                                  <table className="min-w-full text-xs text-left border-collapse table-fixed">
                                    <thead>
                                      <tr className="bg-white/5 font-bold text-pp-text-muted/50 border-b border-pp-border">
                                        <th className="w-10 p-2 border-r border-pp-border text-center">#</th>
                                        {sheet.rows[0]?.map((_: any, i: number) => (
                                          <th key={i} className="p-2 border-r border-pp-border last:border-0 w-32 uppercase tracking-wider">{String.fromCharCode(65 + i)}</th>
                                        ))}
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {sheet.rows.map((row: string[], rIdx: number) => (
                                        <tr key={rIdx} className="border-b border-pp-border/50 last:border-0 hover:bg-pp-accent/5 transition-colors">
                                          <td className="p-2 border-r border-pp-border bg-white/5 text-center font-mono text-[10px] text-pp-text-muted">{rIdx + 1}</td>
                                          {row.map((cell: string, cIdx: number) => (
                                            <td key={cIdx} className="p-2 border-r border-pp-border/50 last:border-0 align-top">
                                              <span className="break-words line-clamp-3 hover:line-clamp-none transition-all">{cell}</span>
                                            </td>
                                          ))}
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : resultPreview.type === 'document' ? (
                          <div className="bg-pp-bg rounded-xl border border-pp-border/50 p-4 max-h-[300px] overflow-y-auto">
                            <div className="text-sm font-mono text-pp-text break-words whitespace-pre-wrap leading-relaxed">
                              {resultPreview.text}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    )}

                    {/* Download Button */}
                    <div className="bg-pp-bg border border-pp-border rounded-xl p-4 flex items-center gap-4">
                      <div className="w-12 h-12 rounded-lg bg-pp-accent/10 flex items-center justify-center text-pp-accent">
                        <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                      </div>
                      <div className="flex-1 overflow-hidden">
                        <p className="text-sm font-semibold truncate text-white">{filename || 'Result'}</p>
                        <p className="text-xs text-pp-text-muted">Ready for download</p>
                      </div>
                      <button 
                        onClick={handleDownloadResult}
                        className="bg-pp-accent hover:bg-pp-accent-light text-pp-bg px-5 py-2.5 rounded-lg text-xs font-bold transition-all shadow-lg"
                      >
                        DOWNLOAD
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm break-words whitespace-pre-wrap leading-relaxed">
                    {msg.content}
                  </p>
                )}
              </div>
            </div>
          );
        })}

        {/* Pending Instruction Bubble (shown immediately on "Send to AI" click) */}
        {pendingInstruction && (
          <div className="flex gap-4 flex-row-reverse animate-in fade-in slide-in-from-bottom-2">
            <div className="w-8 h-8 rounded-full bg-pp-bg border border-pp-border flex items-center justify-center shrink-0">
              <svg className="w-4 h-4 text-pp-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
            <div className="bg-pp-accent rounded-2xl p-4 max-w-2xl shadow-sm rounded-tr-sm text-pp-bg font-medium opacity-70">
              <p className="text-sm break-words whitespace-pre-wrap leading-relaxed">{pendingInstruction}</p>
            </div>
          </div>
        )}

        {/* Pending Chat Message Bubble */}
        {pendingChatMessage && (
          <div className="flex gap-4 flex-row-reverse animate-in fade-in slide-in-from-bottom-2">
            <div className="w-8 h-8 rounded-full bg-pp-bg border border-pp-border flex items-center justify-center shrink-0">
              <svg className="w-4 h-4 text-pp-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
            <div className="bg-pp-accent rounded-2xl p-4 max-w-2xl shadow-sm rounded-tr-sm text-pp-bg font-medium opacity-70">
              <p className="text-sm break-words whitespace-pre-wrap leading-relaxed">{pendingChatMessage}</p>
            </div>
          </div>
        )}

        {/* Processing State Bubble */}
        {taskStatus === 'processing' && (
           <div className="flex gap-4 animate-in fade-in slide-in-from-bottom-4">
            <div className="w-8 h-8 rounded-full bg-pp-accent flex items-center justify-center shrink-0">
               <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div className="max-w-2xl w-full">
              <div className="bg-pp-surface border border-pp-border rounded-2xl rounded-tl-sm p-4 text-pp-text shadow-sm">
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 border-2 border-pp-accent border-t-transparent rounded-full animate-spin" />
                    <span className="text-sm text-pp-text-muted">Scanning your prompt for sensitive data before sending to AI provider...</span>
                  </div>
                  <p className="text-xs text-pp-text-muted/60 pl-7">Your message is being anonymized in real-time. No raw PII will leave your environment.</p>
                </div>
              </div>
            </div>
           </div>
        )}

        {/* Dummy element for auto-scroll */}
        <div ref={chatEndRef} className="h-4" />
      </div>

      {/* Input Area (Integrated Bottom Bar) */}
      <div className="absolute bottom-0 w-full left-1/2 -translate-x-1/2 bg-pp-bg/95 backdrop-blur-md border-t border-pp-border pb-8 pt-4 px-6">
        <div className="max-w-4xl mx-auto">
        {step === 'input' && !selectedFile ? (
           <div className="relative">
             <textarea
               ref={inputTextareaRef}
               value={inputText}
               onChange={(e) => { setInputText(e.target.value); autoResize(inputTextareaRef.current); }}
               placeholder="Type text to anonymize..."
               className="w-full bg-pp-surface border border-pp-border rounded-xl pl-5 pr-24 py-4 text-sm text-white placeholder-pp-text-muted/60 resize-none focus:outline-none focus:border-pp-accent transition-colors shadow-inner leading-tight overflow-hidden"
               style={{ height: '64px' }}
               onKeyDown={(e) => {
                 if (e.key === 'Enter' && !e.shiftKey) {
                   e.preventDefault();
                   if (inputText.trim()) handleSubmitInitial();
                 }
               }}
             />
             
             <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-2">
                <div className="relative">
                  <input
                    type="file"
                    id="file-upload-input"
                    className="hidden"
                    onChange={handleFileChange}
                  />
                  <label
                    htmlFor="file-upload-input"
                    className="p-2 text-pp-text-muted hover:text-pp-accent transition-colors cursor-pointer group"
                    title="Add file"
                  >
                    <svg className="w-5 h-5 group-hover:scale-110 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.414a4 4 0 00-5.656-5.656l-6.415 6.414a6 6 0 108.486 8.486L20.5 13" />
                    </svg>
                  </label>
                </div>

                <button
                  disabled={!inputText.trim() || sendChatMutation.isPending}
                  onClick={handleSubmitInitial}
                  className="w-8 h-8 bg-pp-accent hover:bg-pp-accent-light text-white rounded-lg flex items-center justify-center transition-all disabled:opacity-50 disabled:bg-pp-border"
                >
                  <svg className="w-4 h-4 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                </button>
             </div>
           </div>
        ) : step === 'input' && selectedFile ? (
           <div className="flex items-center justify-between bg-pp-surface border border-pp-border rounded-xl px-5 py-4 shadow-inner min-h-[64px]">
              <div className="flex items-center gap-3">
                <svg className="w-5 h-5 text-pp-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <div>
                   <p className="text-sm font-medium text-white">{selectedFile.name}</p>
                   <p className="text-xs text-pp-text-muted">{formatFileSize(selectedFile.size)}</p>
                </div>
              </div>
              
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setSelectedFile(null)}
                  className="p-2 text-pp-text-muted hover:text-red-400 transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
                <button
                   onClick={handleSubmitInitial}
                   className="px-4 py-1.5 bg-pp-accent hover:bg-pp-accent-light text-pp-bg text-sm font-bold rounded-lg transition-all"
                 >
                   Upload file
                 </button>
              </div>
           </div>
        ) : step === 'done' ? (
            <div className="relative">
              <textarea
                ref={chatTextareaRef}
                value={chatInput}
                onChange={(e) => { setChatInput(e.target.value); autoResize(chatTextareaRef.current); }}
                disabled={sendChatMutation.isPending || taskStatus === 'processing'}
                placeholder="Write another message in the same context to continue the discussion..."
                className="w-full bg-pp-surface border border-pp-border rounded-xl pl-5 pr-16 py-4 text-sm text-white placeholder-pp-text-muted/60 resize-none focus:outline-none focus:border-pp-accent transition-colors disabled:opacity-50 shadow-inner leading-tight overflow-hidden"
                style={{ height: '64px' }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (chatInput.trim()) sendChatMutation.mutate(chatInput);
                  }
                }}
              />
              
              <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center">
                 <button
                   disabled={!chatInput.trim() || sendChatMutation.isPending || taskStatus === 'processing'}
                   onClick={() => sendChatMutation.mutate(chatInput)}
                   className="w-8 h-8 bg-pp-accent hover:bg-pp-accent-light text-white rounded-lg flex items-center justify-center transition-all disabled:opacity-50 disabled:bg-pp-border disabled:hover:bg-pp-border"
                 >
                   <svg className="w-4 h-4 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                     <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                   </svg>
                 </button>
              </div>
            </div>
        ) : null}
        </div>
      </div>
    </div>
  );
}

export default NewTask;
