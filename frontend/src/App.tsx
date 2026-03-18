import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import NewTask from './pages/NewTask';
import History from './pages/History';
import AuditLog from './pages/AuditLog';
import Settings from './pages/Settings';
import keycloak from './auth/keycloak';

function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-pp-bg text-pp-text">
        {/* Sidebar */}
        <aside className="w-64 bg-pp-surface border-r border-pp-border flex flex-col shrink-0">
          {/* Logo */}
          <div className="p-6 border-b border-pp-border">
            <h1 className="text-xl font-bold text-white tracking-widest uppercase">Moretta</h1>
            <p className="text-[10px] text-pp-accent-light opacity-80 mt-1 uppercase tracking-[0.2em] font-medium">v0.5</p>
            <div className="mt-4 text-xs text-pp-text-muted">
              <div className="truncate">{keycloak.tokenParsed?.preferred_username ?? 'authenticated-user'}</div>
              <button
                onClick={() => keycloak.logout({ redirectUri: window.location.origin })}
                className="mt-2 px-2 py-1 text-[10px] uppercase tracking-wider border border-pp-border rounded hover:bg-pp-surface-light"
              >
                Sign out
              </button>
            </div>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-1">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-pp-accent text-pp-bg font-semibold shadow-sm'
                    : 'text-pp-text-muted hover:bg-pp-surface-light hover:text-pp-text'
                }`
              }
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              New chat
            </NavLink>

            <NavLink
              to="/history"
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-pp-accent text-pp-bg font-semibold shadow-sm'
                    : 'text-pp-text-muted hover:bg-pp-surface-light hover:text-pp-text'
                }`
              }
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              History
            </NavLink>

            <div className="pt-4 pb-2">
              <p className="px-4 text-xs font-semibold text-pp-text-muted uppercase tracking-wider">
                Administration
              </p>
            </div>

            <NavLink
              to="/settings"
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-pp-accent text-pp-bg font-semibold shadow-sm'
                    : 'text-pp-text-muted hover:bg-pp-surface-light hover:text-pp-text'
                }`
              }
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37a1.724 1.724 0 002.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              Settings
            </NavLink>

            <NavLink
              to="/audit"
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-pp-accent text-pp-bg font-semibold shadow-sm'
                    : 'text-pp-text-muted hover:bg-pp-surface-light hover:text-pp-text'
                }`
              }

            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Audit logs
            </NavLink>
          </nav>
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/" element={<NewTask />} />
            <Route path="/history" element={<History />} />
            <Route path="/audit" element={<AuditLog />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
