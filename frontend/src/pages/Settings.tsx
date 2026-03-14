import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

interface Provider {
  id: string;
  name: string;
  model: string;
  configured: boolean;
}

function Settings() {
  const [activeTab, setActiveTab] = useState<'providers' | 'pii' | 'model'>('providers');

  const { data: providersData } = useQuery<{ providers: Provider[]; default: string }>({
    queryKey: ['providers'],
    queryFn: async () => {
      const res = await fetch('/api/providers');
      if (!res.ok) throw new Error('Failed to fetch providers');
      return res.json();
    },
  });

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h2 className="text-2xl font-semibold text-white mb-8">Ustawienia</h2>

      {/* Tabs */}
      <div className="flex gap-1 bg-pp-surface border border-pp-border rounded-xl p-1 mb-8">
        {[
          { id: 'providers' as const, label: 'Providerzy AI' },
          { id: 'pii' as const, label: 'Reguły PII' },
          { id: 'model' as const, label: 'Model lokalny' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 py-2.5 px-4 text-sm font-medium rounded-lg transition-all duration-200 ${
              activeTab === tab.id
                ? 'bg-pp-accent text-pp-bg shadow-lg shadow-pp-accent/20'
                : 'text-pp-text-muted hover:text-pp-text'
            }`  }
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Providers Tab */}
      {activeTab === 'providers' && (
        <div className="space-y-4">
          <p className="text-sm text-pp-text-muted mb-6">
            Klucze API do zewnętrznych providerów AI. Konfigurowane przez zmienne środowiskowe (.env).
          </p>

          {providersData?.providers.map((provider) => (
            <div
              key={provider.id}
              className="bg-pp-surface border border-pp-border rounded-xl p-5 flex items-center justify-between"
            >
              <div>
                <div className="flex items-center gap-3">
                  <h3 className="text-white font-medium">{provider.name}</h3>
                  {providersData.default === provider.id && (
                    <span className="text-[10px] bg-pp-accent/20 text-pp-accent border border-pp-accent/30 px-2 py-0.5 rounded-full uppercase tracking-wider font-bold">
                      domyślny
                    </span>
                  )}
                </div>
                {provider.model && (
                  <p className="text-xs text-pp-text-muted mt-1 font-mono">{provider.model}</p>
                )}
              </div>
              <div className="flex items-center gap-2">
                {provider.configured ? (
                  <span className="flex items-center gap-1.5 text-green-400 text-xs font-medium">
                    <div className="w-2 h-2 bg-green-400 rounded-full" />
                    Skonfigurowany
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-pp-text-muted text-xs">
                    <div className="w-2 h-2 bg-pp-text-muted rounded-full" />
                    Brak klucza API
                  </span>
                )}
              </div>
            </div>
          ))}

          <div className="mt-6 p-4 bg-pp-surface-light border border-pp-border rounded-xl">
            <p className="text-xs text-pp-text-muted">
              <strong className="text-pp-text">Jak skonfigurować?</strong> Ustaw zmienne środowiskowe w pliku <code className="bg-pp-bg px-1.5 py-0.5 rounded text-pp-green-text">.env</code>:
            </p>
            <pre className="mt-2 text-[13px] font-mono text-[#f5f5f5] bg-[#050408] border border-pp-border/50 rounded-lg p-5 overflow-x-auto shadow-2xl leading-relaxed">
              <div className="opacity-50"># Configuration keys</div>
              <div><span className="text-pp-accent">ANTHROPIC_API_KEY</span>=sk-ant-...</div>
              <div><span className="text-pp-accent">OPENAI_API_KEY</span>=sk-...</div>
              <div><span className="text-pp-accent">GOOGLE_AI_API_KEY</span>=AI...</div>
              <div><span className="text-pp-accent">DEFAULT_PROVIDER</span>=claude</div>
            </pre>
          </div>
        </div>
      )}

      {/* PII Rules Tab */}
      {activeTab === 'pii' && (
        <div className="space-y-4">
          <p className="text-sm text-pp-text-muted mb-6">
            Typy danych poufnych wykrywane przez system. Presidio wykrywa standardowe PII,
            a model lokalny (Ollama) identyfikuje dane kontekstowe.
          </p>

          <div className="bg-pp-surface border border-pp-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-pp-border">
                  <th className="text-left px-5 py-3 text-xs font-semibold text-pp-text-muted uppercase">Typ</th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-pp-text-muted uppercase">Źródło</th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-pp-text-muted uppercase">Priorytet</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { type: 'Imię i nazwisko', source: 'Presidio', severity: 'critical' },
                  { type: 'PESEL / NIP', source: 'Presidio', severity: 'critical' },
                  { type: 'Adres e-mail', source: 'Presidio', severity: 'critical' },
                  { type: 'Numer telefonu', source: 'Presidio', severity: 'critical' },
                  { type: 'IBAN / Karta kredytowa', source: 'Presidio', severity: 'critical' },
                  { type: 'Adres zamieszkania', source: 'Presidio', severity: 'warning' },
                  { type: 'Kwoty finansowe', source: 'Ollama LLM', severity: 'warning' },
                  { type: 'Kody projektów', source: 'Ollama LLM', severity: 'info' },
                  { type: 'Nazwy klientów', source: 'Ollama LLM', severity: 'warning' },
                  { type: 'Numery umów', source: 'Ollama LLM', severity: 'info' },
                ].map((rule, i) => (
                  <tr key={i} className="border-b border-pp-border/50 hover:bg-pp-surface-light transition-colors">
                    <td className="px-5 py-3 text-white font-medium">{rule.type}</td>
                    <td className="px-5 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        rule.source === 'Presidio' ? 'bg-blue-900/40 text-blue-400' : 'bg-purple-900/40 text-purple-400'
                      }`}>
                        {rule.source}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <span className={`px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider ${
                        rule.severity === 'critical' ? 'bg-red-900/40 text-red-400 border border-red-900/50' :
                        rule.severity === 'warning' ? 'bg-yellow-900/40 text-yellow-400 border border-yellow-900/50' :
                        'bg-pp-border/50 text-pp-text-muted'
                      }`}>
                        {rule.severity === 'critical' ? 'Krytyczny' : rule.severity === 'warning' ? 'Ostrzeżenie' : 'Informacja'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Model Tab */}
      {activeTab === 'model' && (
        <div className="space-y-4">
          <p className="text-sm text-pp-text-muted mb-6">
            Lokalny model AI używany do kontekstowej detekcji danych poufnych specyficznych dla firmy.
          </p>

          <div className="bg-pp-surface border border-pp-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-pp-border">
                  <th className="text-left px-5 py-3 text-xs font-semibold text-pp-text-muted uppercase">Model</th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-pp-text-muted uppercase">RAM</th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-pp-text-muted uppercase">GPU</th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-pp-text-muted uppercase">Jakość</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { name: 'phi4-mini', ram: '4 GB', gpu: 'Nie wymagany', quality: '★★★★★', active: true, recommended: true, desc: 'Lekki i potężny (3.8B), świetny w rozumowaniu' },
                  { name: 'deepseek-r1:8b', ram: '8 GB', gpu: 'Zalecany', quality: '★★★★★', active: false, recommended: false, desc: 'Zaawansowane myślenie (CoT), wybitny w PII i logice' },
                  { name: 'qwen2.5:7b', ram: '8 GB', gpu: 'Zalecany', quality: '★★★★★', active: false, recommended: false, desc: 'Najlepszy model uniwersalny (7B) dzisiejszych czasów' },
                  { name: 'llama3.3:8b', ram: '8 GB', gpu: 'Zalecany', quality: '★★★★☆', active: false, recommended: false, desc: 'Niezawodny i szybki standard od firmy Meta' },
                ].map((model) => (
                  <tr
                    key={model.name}
                    className={`border-b border-pp-border/50 transition-colors ${
                      model.active ? 'bg-pp-green/10' : 'hover:bg-pp-surface-light'
                    }`}
                  >
                    <td className="px-5 py-3 font-mono text-white flex items-center flex-wrap gap-2">
                      <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                          {model.name}
                          {model.recommended && (
                            <span className="text-xs bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 px-2 py-0.5 rounded-full whitespace-nowrap">
                              🔥 Najlepszy wybór
                            </span>
                          )}
                          {model.active && (
                            <span className="ml-2 text-[10px] bg-pp-accent/20 text-pp-accent border border-pp-accent/30 px-2 py-0.5 rounded-full uppercase tracking-wider font-bold">
                          aktywny
                        </span>
                          )}
                        </div>
                        <span className="text-xs text-pp-text-muted mt-1 font-sans">{model.desc}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-pp-text">{model.ram}</td>
                    <td className="px-5 py-3 text-pp-text">{model.gpu}</td>
                    <td className="px-5 py-3 text-yellow-400">{model.quality}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 p-4 bg-pp-surface-light border border-pp-border rounded-xl">
            <p className="text-xs text-pp-text-muted">
              Zmień model ustawiając <code className="bg-pp-bg px-1.5 py-0.5 rounded text-pp-green-text">LOCAL_MODEL</code> w pliku <code className="bg-pp-bg px-1.5 py-0.5 rounded text-pp-green-text">.env</code> i restartując kontener Ollama.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export default Settings;
