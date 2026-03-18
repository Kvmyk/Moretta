import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import './index.css';
import keycloak from './auth/keycloak';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const root = ReactDOM.createRoot(document.getElementById('root')!);

keycloak
  .init({
    onLoad: 'login-required',
    pkceMethod: 'S256',
    checkLoginIframe: false,
  })
  .then((authenticated) => {
    if (!authenticated) {
      keycloak.login();
      return;
    }

    root.render(
      <React.StrictMode>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </React.StrictMode>,
    );
  })
  .catch(() => {
    root.render(
      <div className="h-screen w-screen flex items-center justify-center bg-pp-bg text-pp-text">
        Failed to initialize SSO. Check Keycloak connection.
      </div>,
    );
  });
