interface AuditTrailProps {
  fileLoaded: boolean;
  piiCount: number;
  dataLeftBoundary: number;
}

function AuditTrail({ fileLoaded, piiCount, dataLeftBoundary }: AuditTrailProps) {
  return (
    <div className="border-t border-pp-border pt-5 mt-2">
      <h4 className="text-xs font-semibold text-pp-text-muted uppercase tracking-wider mb-3">
        Ślad audytu
      </h4>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm text-pp-text">Plik wczytany lokalnie</span>
          {fileLoaded ? (
            <span className="text-sm font-medium text-green-400">OK</span>
          ) : (
            <span className="text-sm text-pp-text-muted">—</span>
          )}
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-pp-text">PII wykryte (Presidio + Mistral:7b)</span>
          <span className="text-sm font-medium text-pp-text">
            {piiCount > 0 ? `${piiCount} pól` : '—'}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-pp-text">Dane poufne poza granicą</span>
          <span className={`text-sm font-bold ${dataLeftBoundary === 0 ? 'text-green-400' : 'text-red-400'}`}>
            {dataLeftBoundary}
          </span>
        </div>
      </div>
    </div>
  );
}

export default AuditTrail;
