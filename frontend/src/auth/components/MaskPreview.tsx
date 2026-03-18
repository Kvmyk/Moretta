interface MaskPreviewProps {
  text: string;
  isLoading: boolean;
  tokensUsed: number;
  onClose: () => void;
}

function MaskPreview({ text, isLoading, tokensUsed, onClose }: MaskPreviewProps) {
  // Highlight tokens in the text
  const highlightTokens = (input: string) => {
    const tokenRegex = /\[[A-ZĄĆĘŁŃÓŚŹŻ_]+_[a-f0-9]{4}\]/g;
    const parts: { text: string; isToken: boolean }[] = [];
    let lastIndex = 0;

    let match;
    while ((match = tokenRegex.exec(input)) !== null) {
      if (match.index > lastIndex) {
        parts.push({ text: input.slice(lastIndex, match.index), isToken: false });
      }
      parts.push({ text: match[0], isToken: true });
      lastIndex = match.index + match[0].length;
    }
    if (lastIndex < input.length) {
      parts.push({ text: input.slice(lastIndex), isToken: false });
    }

    return parts;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-pp-surface border border-pp-border rounded-2xl shadow-2xl w-full max-w-3xl max-h-[80vh] flex flex-col mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-pp-border">
          <div>
            <h3 className="text-lg font-semibold text-white">Podgląd maski</h3>
            <p className="text-xs text-pp-text-muted mt-0.5">
              {tokensUsed} tokenów zastępczych użytych
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-pp-text-muted hover:text-white hover:bg-pp-surface-light transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-6 h-6 border-2 border-pp-accent border-t-transparent rounded-full animate-spin" />
              <span className="ml-3 text-sm text-pp-text-muted">Generowanie podglądu...</span>
            </div>
          ) : (
            <div className="font-mono text-sm leading-relaxed whitespace-pre-wrap break-words">
              {highlightTokens(text).map((part, i) =>
                part.isToken ? (
                  <span
                    key={i}
                    className="inline-block bg-pp-accent/30 text-pp-green-text px-1.5 py-0.5 rounded mx-0.5 font-bold text-xs"
                  >
                    {part.text}
                  </span>
                ) : (
                  <span key={i} className="text-pp-text">{part.text}</span>
                )
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-pp-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-pp-green-text rounded-full" />
            <span className="text-xs text-pp-text-muted">
              Wszystkie dane poufne zastąpione tokenami UUID
            </span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-pp-surface-light border border-pp-border rounded-lg text-sm font-medium text-pp-text hover:bg-pp-border transition-colors"
          >
            Zamknij
          </button>
        </div>
      </div>
    </div>
  );
}

export default MaskPreview;
