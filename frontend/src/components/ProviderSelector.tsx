import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';

interface Model {
  id: string;
  name: string;
  tier: string;
  context: number;
}

interface Provider {
  id: string;
  name: string;
  configured: boolean;
  default_model: string;
  models: Model[];
}

interface ProvidersResponse {
  providers: Provider[];
  default_provider: string;
  default_model: string;
}

interface ProviderSelectorProps {
  provider: string;
  model: string;
  onProviderChange: (provider: string) => void;
  onModelChange: (model: string) => void;
}

const tierLabel: Record<string, string> = {
  flagship: 'Flagship',
  standard: 'Standard',
  fast: 'Fast',
  codex: 'Codex',
  legacy: 'Legacy',
};

function ProviderSelector({ provider, model, onProviderChange, onModelChange }: ProviderSelectorProps) {
  const { data } = useQuery<ProvidersResponse>({
    queryKey: ['providers'],
    queryFn: async () => {
      const res = await fetch('/api/providers');
      if (!res.ok) throw new Error('Failed to fetch providers');
      return res.json();
    },
  });

  // On first load: pick the first configured provider if current selection isn't configured
  useEffect(() => {
    if (!data) return;
    const current = data.providers.find((p) => p.id === provider);
    if (!current?.configured) {
      const firstConfigured = data.providers.find((p) => p.configured);
      if (firstConfigured) {
        onProviderChange(firstConfigured.id);
        onModelChange(firstConfigured.default_model);
      }
    }
  }, [data]);

  // When provider changes, reset model if it doesn't belong to the new provider
  useEffect(() => {
    if (!data) return;
    const p = data.providers.find((pr) => pr.id === provider);
    if (p) {
      const belongsToProvider = p.models.some((m) => m.id === model);
      if (!belongsToProvider) {
        onModelChange(p.default_model);
      }
    }
  }, [provider, data]);

  // Only show configured providers in the dropdown
  const configuredProviders = data?.providers?.filter((p) => p.configured) ?? [];
  const currentProvider = configuredProviders.find((p) => p.id === provider);

  // Group models by tier for the current provider
  const groupedModels: Record<string, Model[]> = {};
  if (currentProvider?.models) {
    for (const m of currentProvider.models) {
      const tier = m.tier || 'other';
      if (!groupedModels[tier]) groupedModels[tier] = [];
      groupedModels[tier].push(m);
    }
  }

  if (!data) {
    return (
      <div className="flex items-center gap-3">
        <span className="text-sm text-pp-text-muted">Loading...</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      {/* Provider select */}
      <div className="relative">
        <select
          value={provider}
          onChange={(e) => onProviderChange(e.target.value)}
          className="appearance-none bg-pp-surface border border-pp-border rounded-lg pl-3 pr-8 py-2 text-sm font-medium text-white cursor-pointer hover:border-pp-accent/50 focus:outline-none focus:border-pp-accent transition-all duration-300 shadow-lg shadow-black/20"
        >
          {configuredProviders.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <svg className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-pp-text-muted pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>

      {/* Model select */}
      <div className="relative">
        <select
          value={model}
          onChange={(e) => onModelChange(e.target.value)}
          className="appearance-none bg-pp-surface border border-pp-border rounded-lg pl-3 pr-8 py-2 text-sm text-pp-text cursor-pointer hover:border-pp-accent/50 focus:outline-none focus:border-pp-accent transition-all duration-300 shadow-lg shadow-black/20 max-w-[260px]"
        >
          {Object.entries(groupedModels).map(([tier, models]) => (
            <optgroup key={tier} label={tierLabel[tier] || tier}>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        <svg className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-pp-text-muted pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>
    </div>
  );
}

export default ProviderSelector;
