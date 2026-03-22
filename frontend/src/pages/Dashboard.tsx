import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../auth/apiFetch';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area
} from 'recharts';

interface DashboardData {
  stats: {
    total_files: number;
    total_tasks: number;
    total_pii_detected: number;
    security_incidents: number;
    active_sessions: number;
    active_tasks: number;
  };
  pii_breakdown: { type: string; count: number }[];
  provider_usage: { provider: string; count: number }[];
  daily_activity: { date: string; count: number }[];
}

const CHART_COLORS = [
  '#b8afc8', '#8b7fad', '#6c5f91', '#e8d5b7',
  '#c4a882', '#a3e4d7', '#85c1e9', '#f1948a',
  '#82e0aa', '#f0b27a', '#bb8fce', '#73c6b6',
];

const PROVIDER_LABELS: Record<string, string> = {
  claude: 'Claude',
  openai: 'GPT',
  gemini: 'Gemini',
  ollama: 'Ollama',
  openrouter: 'OpenRouter',
};

function Dashboard() {
  const { data, isLoading, error } = useQuery<DashboardData>({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const res = await apiFetch('/api/dashboard');
      if (!res.ok) throw new Error('Failed to fetch dashboard');
      return res.json();
    },
    refetchInterval: 30000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex items-center gap-3 text-pp-text-muted">
          <div className="w-5 h-5 border-2 border-pp-accent border-t-transparent rounded-full animate-spin" />
          Loading dashboard...
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-red-400">Failed to load dashboard data.</p>
      </div>
    );
  }

  const { stats, pii_breakdown, provider_usage, daily_activity } = data;

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white">Dashboard</h2>
        <p className="text-sm text-pp-text-muted mt-1">Real-time overview of your Moretta instance</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard
          label="Files processed"
          value={stats.total_files}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          }
        />
        <StatCard
          label="AI tasks"
          value={stats.total_tasks}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          }
        />
        <StatCard
          label="PII detected"
          value={stats.total_pii_detected}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          }
          accent
        />
        <StatCard
          label="Security alerts"
          value={stats.security_incidents}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          }
          danger={stats.security_incidents > 0}
        />
        <StatCard
          label="Active sessions"
          value={stats.active_sessions}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5.121 17.804A13.937 13.937 0 0112 16c2.5 0 4.847.655 6.879 1.804M15 10a3 3 0 11-6 0 3 3 0 016 0zm6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
        />
        <StatCard
          label="Tasks in queue"
          value={stats.active_tasks}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          }
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* PII Breakdown */}
        <div className="bg-pp-surface border border-pp-border rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-white mb-4 uppercase tracking-wider">
            PII Types Detected
          </h3>
          {pii_breakdown.length > 0 ? (
            <div className="flex items-center gap-4">
              <div className="w-48 h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pii_breakdown}
                      dataKey="count"
                      nameKey="type"
                      cx="50%"
                      cy="50%"
                      innerRadius={40}
                      outerRadius={80}
                      paddingAngle={2}
                    >
                      {pii_breakdown.map((_, idx) => (
                        <Cell key={idx} fill={CHART_COLORS[idx % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: '#1a1625',
                        border: '1px solid rgba(184,175,200,0.2)',
                        borderRadius: '12px',
                        fontSize: '12px',
                        color: '#e8e6ed',
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="flex-1 space-y-2">
                {pii_breakdown.map((item, idx) => (
                  <div key={item.type} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ backgroundColor: CHART_COLORS[idx % CHART_COLORS.length] }}
                      />
                      <span className="text-pp-text-muted">{item.type}</span>
                    </div>
                    <span className="font-mono text-white">{item.count}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-pp-text-muted text-center py-8">
              No PII data yet. Upload a document to see detection stats.
            </p>
          )}
        </div>

        {/* Provider Usage */}
        <div className="bg-pp-surface border border-pp-border rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-white mb-4 uppercase tracking-wider">
            AI Provider Usage
          </h3>
          {provider_usage.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={provider_usage.map(p => ({
                ...p,
                provider: PROVIDER_LABELS[p.provider] || p.provider,
              }))}>
                <XAxis
                  dataKey="provider"
                  tick={{ fill: '#8b8898', fontSize: 11 }}
                  axisLine={{ stroke: 'rgba(184,175,200,0.15)' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: '#8b8898', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: '#1a1625',
                    border: '1px solid rgba(184,175,200,0.2)',
                    borderRadius: '12px',
                    fontSize: '12px',
                    color: '#e8e6ed',
                  }}
                  itemStyle={{ color: '#e8e6ed' }}
                  cursor={{ fill: 'rgba(255, 255, 255, 0.04)' }}
                />
                <Bar dataKey="count" fill="#b8afc8" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-pp-text-muted text-center py-8">
              No AI tasks yet. Create a task to see provider usage.
            </p>
          )}
        </div>
      </div>

      {/* Activity Timeline */}
      <div className="bg-pp-surface border border-pp-border rounded-2xl p-6">
        <h3 className="text-sm font-semibold text-white mb-4 uppercase tracking-wider">
          Activity (Last 30 Days)
        </h3>
        {daily_activity.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={daily_activity}>
              <defs>
                <linearGradient id="activityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#b8afc8" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#b8afc8" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                tick={{ fill: '#8b8898', fontSize: 10 }}
                axisLine={{ stroke: 'rgba(184,175,200,0.15)' }}
                tickLine={false}
                tickFormatter={(d: string) => d.slice(5)} // MM-DD
              />
              <YAxis
                tick={{ fill: '#8b8898', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  background: '#1a1625',
                  border: '1px solid rgba(184,175,200,0.2)',
                  borderRadius: '12px',
                  fontSize: '12px',
                  color: '#e8e6ed',
                }}
                itemStyle={{ color: '#e8e6ed' }}
                labelFormatter={(label: any) => `Date: ${label}`}
                cursor={{ stroke: 'rgba(255, 255, 255, 0.1)', strokeWidth: 1, strokeDasharray: '4 4' }}
              />
              <Area
                type="monotone"
                dataKey="count"
                stroke="#b8afc8"
                strokeWidth={2}
                fill="url(#activityGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-pp-text-muted text-center py-8">
            No activity data yet. Start processing documents to see the timeline.
          </p>
        )}
      </div>
    </div>
  );
}


function StatCard({
  label,
  value,
  icon,
  accent,
  danger,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  accent?: boolean;
  danger?: boolean;
}) {
  return (
    <div className={`
      bg-pp-surface border rounded-2xl p-5 flex flex-col gap-3
      transition-all duration-200 hover:shadow-lg hover:shadow-pp-accent/5
      ${danger ? 'border-red-500/30' : 'border-pp-border'}
    `}>
      <div className={`
        w-9 h-9 rounded-xl flex items-center justify-center
        ${danger ? 'bg-red-500/10 text-red-400' : accent ? 'bg-pp-accent/10 text-pp-accent' : 'bg-white/5 text-pp-text-muted'}
      `}>
        {icon}
      </div>
      <div>
        <p className={`text-2xl font-bold ${danger ? 'text-red-400' : 'text-white'}`}>
          {value.toLocaleString()}
        </p>
        <p className="text-xs text-pp-text-muted mt-0.5">{label}</p>
      </div>
    </div>
  );
}

export default Dashboard;
