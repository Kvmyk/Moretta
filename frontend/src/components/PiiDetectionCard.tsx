import { useState } from 'react';

interface PiiType {
  type: string;
  label: string;
  count: number;
  severity: 'critical' | 'warning' | 'info';
  matches?: string[];
}

interface PiiDetectionCardProps {
  types: PiiType[];
}

function PiiDetectionCard({ types }: PiiDetectionCardProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggleExpand = (type: string) => {
    setExpanded((prev) => ({ ...prev, [type]: !prev[type] }));
  };

  const severityDot = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'bg-pp-badge-red';
      case 'warning':
        return 'bg-pp-badge-yellow';
      default:
        return 'bg-pp-badge-gray';
    }
  };

  if (!types.length) {
    return (
      <div className="py-4">
        <p className="text-sm text-pp-text-muted">Nie wykryto danych poufnych</p>
      </div>
    );
  }

  return (
    <div>
      <h4 className="text-xs font-semibold text-pp-text-muted flex items-center gap-2 mb-3">
        WYKRYTE DANE POUFNE
        <span className="bg-pp-surface-light px-2 py-0.5 rounded-full text-white text-[10px]">
          {types.reduce((acc, curr) => acc + curr.count, 0)}
        </span>
      </h4>
      <div className="space-y-2">
        {types.map((pii) => {
          const isExpanded = expanded[pii.type];
          return (
            <div key={pii.type} className="bg-pp-surface-light rounded-lg border border-pp-border/50 overflow-hidden transition-all duration-200">
              <button
                onClick={() => toggleExpand(pii.type)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-pp-border/30 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className={`w-2 h-2 rounded-full shadow-sm ${severityDot(pii.severity)}`} />
                  <span className="text-sm font-medium text-white">{pii.label}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs font-bold text-pp-text-muted bg-pp-bg px-2.5 py-1 rounded-full min-w-[28px] text-center border border-pp-border/50">
                    {pii.count}
                  </span>
                  <svg
                    className={`w-4 h-4 text-pp-text-muted transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>

              {isExpanded && pii.matches && pii.matches.length > 0 && (
                <div className="px-4 pb-3 pt-1 border-t border-pp-border/30 bg-pp-bg/30">
                  <ul className="space-y-1.5 mt-2">
                    {pii.matches.map((match, idx) => (
                      <li key={idx} className="text-xs text-pp-text bg-pp-surface px-2.5 py-1.5 rounded flex items-center gap-2 border border-pp-border/30">
                        <span className="text-pp-text-muted/50 select-none">•</span>
                        <span className="font-mono text-pp-accent break-all italic">{match}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default PiiDetectionCard;
