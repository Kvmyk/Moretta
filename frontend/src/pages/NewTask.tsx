import { useState, useCallback, useRef, useEffect } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import PiiDetectionCard from '../components/PiiDetectionCard';
import ProviderSelector from '../components/ProviderSelector';

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
  types: PiiType[];
}

interface PreviewResult {
  file_id: string;
  anonymized_text: string;
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
  
  // Input states
  const [inputText, setInputText] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  
  // AI Config
  const [instruction, setInstruction] = useState('');
  const [provider, setProvider] = useState('claude');
  const [model, setModel] = useState('claude-sonnet-4.6-20260217');
  
  // Task states
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };



  // Upload or submit text mutation
  const submitDataMutation = useMutation({
    mutationFn: async () => {
      if (selectedFile) {
        const formData = new FormData();
        formData.append('file', selectedFile);
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        if (!res.ok) throw new Error('Upload failed');
        return res.json() as Promise<UploadResult>;
      } else if (inputText.trim()) {
        const res = await fetch('/api/text', {
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
      const res = await fetch(`/api/file/${fileId}/pii`);
      if (!res.ok) throw new Error('Failed to fetch PII');
      return res.json();
    },
    enabled: !!fileId,
  });

  // Fetch preview for text inputs
  const previewQuery = useQuery<PreviewResult>({
    queryKey: ['preview', fileId],
    queryFn: async () => {
      const res = await fetch(`/api/file/${fileId}/preview`);
      if (!res.ok) throw new Error('Failed to fetch preview');
      return res.json();
    },
    enabled: !!fileId && !selectedFile,
  });

  // Fetch final result for text (only when done and not a file)
  const resultQuery = useQuery<{ result_text: string }>({
    queryKey: ['result', taskId],
    queryFn: async () => {
      const res = await fetch(`/api/task/${taskId}/result`);
      if (!res.ok) throw new Error('Result fetch failed');
      return res.json();
    },
    enabled: !!taskId && taskStatus === 'completed' && !selectedFile,
  });

  useEffect(() => {
    scrollToBottom();
  }, [step, piiQuery?.data, previewQuery?.data, resultQuery?.data, taskStatus]);

  // Create task
  const createTaskMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: fileId,
          instruction: instruction || 'Przetwórz ten tekst i popraw błędy.',
          provider,
          model,
        }),
      });
      if (!res.ok) throw new Error('Task creation failed');
      return res.json() as Promise<TaskResult>;
    },
    onSuccess: (data) => {
      setTaskId(data.task_id);
      setTaskStatus('processing');
      setStep('processing');
      pollTaskStatus(data.task_id);
    },
  });

  // Poll task status
  const pollTaskStatus = useCallback(async (tid: string) => {
    const poll = async () => {
      try {
        const res = await fetch(`/api/task/${tid}/status`);
        const data = await res.json();
        setTaskStatus(data.status);
        if (data.status === 'processing') {
          setTimeout(poll, 2000);
        } else if (data.status === 'completed') {
          setStep('done');
        } else {
          setStep('done'); // Even if failed
        }
      } catch {
        setTaskStatus('failed');
        setStep('done');
      }
    };
    poll();
  }, []);

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
      const res = await fetch(`/api/task/${taskId}/download`);
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
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    return `${Math.round(bytes / 1024)} KB`;
  };

  const renderHighlightedText = (text: string) => {
    // Rozdzielanie po tokenach zaczynających się od [ i kończących się na ] 
    // z alfanumerycznym ID i ew. typem, np: [PERSON_1a2b] lub [DATA_123]
    const parts = text.split(/(\[[A-Z0-9_]+_[a-f0-9]+\])/g);
    return parts.map((part, idx) => {
      if (part.match(/^\[[A-Z0-9_]+_[a-f0-9]+\]$/)) {
        return (
          <span key={idx} className="text-pp-green font-bold bg-pp-green/10 px-1 py-0.5 rounded">
            {part}
          </span>
        );
      }
      return <span key={idx}>{part}</span>;
    });
  };

  return (
    <div className="flex flex-col h-[calc(100vh-2rem)]">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 px-8 py-4 bg-pp-surface rounded-xl border border-pp-border">
        <div>
          <h2 className="text-xl font-semibold text-white">Czat zadania</h2>
          <p className="text-xs text-pp-text-muted mt-1">Bezpieczne przesyłanie poleceń do modeli AI</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-pp-text-muted">Model AI:</span>
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
              Uruchom nowe
            </button>
          )}
        </div>
      </div>

      {/* Chat Messages Area */}
      <div className="flex-1 overflow-y-auto px-8 pb-32 space-y-8 scroll-smooth">
        
        {/* Intro bubble */}
        {step === 'input' && (
          <div className="flex gap-4">
            <div className="w-8 h-8 rounded-full bg-pp-accent flex items-center justify-center shrink-0">
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div className="bg-pp-surface border border-pp-border rounded-2xl rounded-tl-sm p-4 max-w-2xl">
              <p className="text-sm text-pp-text">
                Witaj! Wklej poniżej swój tekst, który chcesz zanonimizować, aby przetworzyć go wybranym modelem AI,
                albo załącz plik (DOCX/XLSX/EML) korzystając z wbudowanej opcji.
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
            <div className="bg-pp-accent text-white rounded-2xl rounded-tr-sm p-4 max-w-2xl shadow-lg">
              {selectedFile ? (
                <div className="flex items-center gap-3">
                  <svg className="w-6 h-6 text-white/70" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                  </svg>
                  <div>
                    <span className="font-medium block">{selectedFile.name}</span>
                    <span className="text-xs text-white/70">{formatFileSize(selectedFile.size)}</span>
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
               <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div className="max-w-2xl w-full">
              {(piiQuery.isLoading || submitDataMutation.isPending) ? (
                <div className="bg-pp-surface border border-pp-border rounded-2xl rounded-tl-sm p-4">
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 border-2 border-pp-accent border-t-transparent rounded-full animate-spin" />
                    <span className="text-sm text-pp-text-muted">Analizuję tekst pod kątem danych wrażliwych...</span>
                  </div>
                </div>
              ) : piiQuery.data ? (
                <div className="space-y-4">
                  <div className="bg-pp-surface border border-pp-border rounded-2xl rounded-tl-sm p-4 shadow-sm">
                    <p className="text-sm text-pp-text mb-4">
                      Zakończyłem skanowanie. Znalazłem {piiQuery.data.total_pii} wrażliwych fragmentów, które zostały ukryte pod tokenami, zanim cokolwiek wyślę do sztucznej inteligencji.
                    </p>
                    <div className="bg-pp-bg rounded-xl border border-pp-border/50 p-3">
                      <PiiDetectionCard types={piiQuery.data.types} />
                    </div>

                    {!selectedFile && previewQuery.data && (
                      <div className="bg-pp-bg rounded-xl border border-pp-border/50 p-4 mt-4">
                        <h5 className="text-xs font-semibold text-pp-text-muted flex items-center gap-2 mb-2">
                          PODGLĄD TEKSTU WYSYŁANEGO DO AI (ZAAOONIMIZOWANY)
                        </h5>
                        <p className="text-sm font-mono text-pp-text break-words whitespace-pre-wrap leading-relaxed">
                          {renderHighlightedText(previewQuery.data.anonymized_text)}
                        </p>
                      </div>
                    )}
                  </div>

                  {step === 'pii_detected' && (
                    <div className="bg-pp-surface border border-pp-border rounded-2xl p-4 shadow-sm animate-in fade-in">
                      <label className="block text-sm font-medium text-pp-text mb-2">
                        Co AI ma zrobić z tym tekstem?
                      </label>
                      <textarea
                        value={instruction}
                        onChange={(e) => setInstruction(e.target.value)}
                        placeholder="Napisz instrukcję, np. Przetłumacz na angielski... (opcjonalnie)"
                        className="w-full h-24 bg-pp-bg border border-pp-border rounded-xl px-4 py-3 text-sm text-white placeholder-pp-text-muted/50 resize-none focus:outline-none focus:border-pp-accent transition-colors mb-4"
                      />
                      <div className="flex justify-end">
                        <button
                          onClick={handleSendToAI}
                          disabled={createTaskMutation.isPending}
                          className="px-6 py-2.5 bg-pp-accent hover:bg-pp-accent-light text-white text-sm font-medium rounded-xl transition-all shadow-md shadow-pp-accent/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                          {createTaskMutation.isPending ? 'Wysyłanie...' : 'Wyślij do AI'}
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="bg-pp-surface border border-red-900/50 rounded-2xl rounded-tl-sm p-4 text-sm text-red-500">
                  Wystąpił błąd podczas analizy PII.
                </div>
              )}
            </div>
          </div>
        )}

        {/* User Instruction Bubble */}
        {(step === 'processing' || step === 'done') && instruction && (
          <div className="flex gap-4 flex-row-reverse animate-in fade-in slide-in-from-bottom-4">
             <div className="w-8 h-8 rounded-full bg-pp-bg border border-pp-border flex items-center justify-center shrink-0">
              <svg className="w-4 h-4 text-pp-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
            <div className="bg-pp-accent text-white rounded-2xl rounded-tr-sm p-4 max-w-2xl shadow-lg">
              <p className="text-sm whitespace-pre-wrap">{instruction}</p>
            </div>
          </div>
        )}

        {/* Final Result Bubble */}
        {(step === 'processing' || step === 'done') && (
           <div className="flex gap-4 animate-in fade-in slide-in-from-bottom-4">
            <div className="w-8 h-8 rounded-full bg-pp-accent flex items-center justify-center shrink-0">
               <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div className="max-w-2xl w-full">
              {taskStatus === 'processing' ? (
                <div className="bg-pp-surface border border-pp-border rounded-2xl rounded-tl-sm p-4">
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 border-2 border-pp-accent border-t-transparent rounded-full animate-spin" />
                    <span className="text-sm text-pp-text-muted">Czekam na odpowiedź wybranego modelu AI...</span>
                  </div>
                </div>
              ) : taskStatus === 'completed' ? (
                <div className="bg-pp-bg border border-pp-accent/50 rounded-2xl rounded-tl-sm p-5 shadow-[0_0_15px_rgba(59,130,246,0.1)]">
                  <div className="flex items-start justify-between">
                    <div>
                      <h4 className="text-sm font-medium text-white mb-1">Zadanie ukończone!</h4>
                      <p className="text-xs text-pp-text-muted">
                        Dane z powrotem podmienione na oryginalne PII.
                        {selectedFile ? ' Możesz pobrać wynik bezpiecznie poniżej.' : ''}
                      </p>
                    </div>
                    <div className="w-10 h-10 rounded-full bg-pp-accent/20 flex items-center justify-center text-pp-accent shrink-0">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                  </div>
                  
                  <div className="mt-6">
                    {selectedFile ? (
                      <button
                        onClick={handleDownloadResult}
                        className="w-full px-4 py-3 bg-pp-surface hover:bg-pp-border border border-pp-border rounded-xl text-white text-sm font-medium transition flex items-center justify-center gap-2 group"
                      >
                        <svg className="w-5 h-5 text-pp-text-muted group-hover:text-white transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        Pobierz dokument z z powrotem jawnymi danymi
                      </button>
                    ) : (
                      <div className="bg-pp-surface/50 border border-pp-border/50 rounded-xl p-4 mt-2">
                        {resultQuery.isLoading ? (
                          <div className="flex items-center gap-2 text-pp-text-muted">
                            <div className="w-4 h-4 border-2 border-pp-accent border-t-transparent rounded-full animate-spin" />
                            <span className="text-sm">Pobieranie wyniku...</span>
                          </div>
                        ) : resultQuery.data ? (
                          <p className="text-sm text-white break-words whitespace-pre-wrap leading-relaxed">
                            {resultQuery.data.result_text}
                          </p>
                        ) : (
                          <p className="text-sm text-red-400">Nie udało się pobrać wyniku.</p>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="bg-red-900/20 border border-red-900/50 rounded-2xl rounded-tl-sm p-4 text-sm text-red-500">
                  Model AI zwrócił błąd. Spróbuj zmienić wybrany model w prawym górnym rogu.
                </div>
              )}
            </div>
           </div>
        )}

        {/* Dummy element for auto-scroll */}
        <div ref={chatEndRef} className="h-4" />
      </div>

      {/* Input Area (Bottom Fixed-like) */}
      <div className="p-4 bg-pp-bg border-t border-pp-border absolute bottom-0 w-full max-w-4xl left-1/2 -translate-x-1/2">
        {!selectedFile ? (
           <div className="relative">
             <textarea
               value={inputText}
               onChange={(e) => setInputText(e.target.value)}
               disabled={step !== 'input'}
               placeholder="Napisz tekst do anonimizacji..."
               className="w-full bg-pp-surface border border-pp-border rounded-2xl pl-5 pr-24 py-4 text-sm text-white placeholder-pp-text-muted/60 resize-none focus:outline-none focus:border-pp-accent transition-colors disabled:opacity-50 h-16 shadow-lg leading-tight"
               onKeyDown={(e) => {
                 if (e.key === 'Enter' && !e.shiftKey) {
                   e.preventDefault();
                   if (step === 'input' && inputText.trim()) handleSubmitInitial();
                 }
               }}
             />
             
             {/* Action buttons inside input */}
             <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
                {/* File Upload Button */}
                <button
                  disabled={step !== 'input'}
                  onClick={() => fileInputRef.current?.click()}
                  className="p-2 text-pp-text-muted hover:text-white transition-colors disabled:opacity-50"
                  title="Załącz plik z dysku"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                     <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                  </svg>
                </button>
                <input
                  type="file"
                  ref={fileInputRef}
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) setSelectedFile(file);
                  }}
                  accept=".docx,.xlsx,.eml,.msg,.txt"
                />
                
                {/* Submit Text Button */}
                <button
                  disabled={step !== 'input' || !inputText.trim()}
                  onClick={handleSubmitInitial}
                  className="w-8 h-8 bg-pp-accent hover:bg-pp-accent-light text-white rounded-xl flex items-center justify-center transition-all disabled:opacity-50 disabled:bg-pp-border disabled:hover:bg-pp-border"
                >
                  <svg className="w-4 h-4 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                </button>
             </div>
           </div>
        ) : (
          <div className="flex items-center justify-between bg-pp-surface border border-pp-border rounded-2xl px-5 py-4 shadow-lg min-h-[64px]">
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
                 disabled={step !== 'input'}
                 onClick={() => setSelectedFile(null)}
                 className="p-2 text-pp-text-muted hover:text-red-400 transition-colors disabled:opacity-50"
               >
                 <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                   <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                 </svg>
               </button>
               <button
                  disabled={step !== 'input'}
                  onClick={handleSubmitInitial}
                  className="px-4 py-1.5 bg-pp-accent hover:bg-pp-accent-light text-white text-sm font-medium rounded-lg transition-all disabled:opacity-50"
                >
                  Prześlij plik
                </button>
             </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default NewTask;
