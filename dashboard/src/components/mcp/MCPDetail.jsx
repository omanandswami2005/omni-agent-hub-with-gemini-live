/**
 * MCP: MCPDetail — Detailed view of a single MCP server.
 */

import { useState, useEffect, useCallback } from 'react';
import MCPToggle from './MCPToggle';
import MCPIcon from './MCPIcon';
import { useMcpStore } from '@/stores/mcpStore';

export default function MCPDetail({ server, onToggle, onClose }) {
  const [oauthLoading, setOauthLoading] = useState(false);
  const [secrets, setSecrets] = useState({});
  const [secretsSaved, setSecretsSaved] = useState(false);
  const [secretsLoading, setSecretsLoading] = useState(false);
  const startOAuth = useMcpStore((s) => s.startOAuth);
  const disconnectOAuth = useMcpStore((s) => s.disconnectOAuth);
  const handleOAuthCallback = useMcpStore((s) => s.handleOAuthCallback);
  const fetchCatalog = useMcpStore((s) => s.fetchCatalog);
  const refreshAfterOAuth = useMcpStore((s) => s.refreshAfterOAuth);
  const saveSecrets = useMcpStore((s) => s.saveSecrets);
  const startGoogleOAuth = useMcpStore((s) => s.startGoogleOAuth);
  const disconnectGoogleOAuth = useMcpStore((s) => s.disconnectGoogleOAuth);

  const isOAuth = server?.kind === 'mcp_oauth';
  const isGoogleOAuth = server?.google_oauth_scopes?.length > 0;
  const isConnected = server?.state === 'connected';
  const needsApiKeys = !isOAuth && !isGoogleOAuth && server?.requires_auth && server?.env_keys?.length > 0;

  // Reset secrets form when server changes
  useEffect(() => {
    setSecrets({});
    setSecretsSaved(false);
  }, [server?.id]);

  // Listen for OAuth popup postMessage
  const onMessage = useCallback((event) => {
    if (event.data?.type === 'oauth_callback' && event.data.plugin_id === server?.id) {
      handleOAuthCallback(event.data.plugin_id, event.data.status);
      setOauthLoading(false);
      // Fetch immediately, then retry with backoff until tools appear
      // (backend tool discovery can be on a different Cloud Run instance)
      fetchCatalog();
      if (event.data.status === 'success') {
        refreshAfterOAuth(event.data.plugin_id);
      }
    }
  }, [server?.id, handleOAuthCallback, fetchCatalog, refreshAfterOAuth]);

  useEffect(() => {
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [onMessage]);

  if (!server) return null;

  const handleOAuthConnect = async () => {
    setOauthLoading(true);
    try {
      if (isGoogleOAuth) {
        await startGoogleOAuth(server.id);
      } else {
        await startOAuth(server.id);
      }
    } catch (err) {
      console.error('OAuth connection error:', err);
      // Show error briefly then reset loading state
      setTimeout(() => setOauthLoading(false), 2000);
    }
    // Reset loading after a timeout in case no callback comes
    setTimeout(() => setOauthLoading(false), 10000);
  };

  const handleOAuthDisconnect = async () => {
    if (isGoogleOAuth) {
      await disconnectGoogleOAuth(server.id);
    } else {
      await disconnectOAuth(server.id);
    }
    fetchCatalog();
  };

  return (
    <div className="space-y-4 rounded-lg border border-border p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <MCPIcon icon={server.icon} name={server.name} size={32} />
          <div>
            <h2 className="text-lg font-medium">{server.name}</h2>
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{server.category}</span>
          </div>
        </div>
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground">✕</button>
      </div>

      <p className="text-sm text-muted-foreground">{server.description}</p>

      {/* OAuth connect / disconnect (MCP OAuth or Google OAuth native) */}
      {(isOAuth || isGoogleOAuth) ? (
        <div className="flex items-center justify-between rounded-lg bg-muted/50 p-3">
          <div>
            <span className="text-sm font-medium">{isGoogleOAuth ? 'Google Account' : 'OAuth Connection'}</span>
            {isConnected && <span className="ml-2 text-xs text-green-500">● Connected</span>}
            {server.state === 'error' && (
              <p className="mt-1 text-xs text-destructive">{server.error}</p>
            )}
          </div>
          {isConnected ? (
            <button
              onClick={handleOAuthDisconnect}
              className="rounded-lg border border-destructive/50 px-3 py-1.5 text-sm text-destructive hover:bg-destructive/10"
            >
              Disconnect
            </button>
          ) : (
            <button
              onClick={handleOAuthConnect}
              disabled={oauthLoading}
              className="rounded-lg bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {oauthLoading ? 'Connecting…' : isGoogleOAuth ? 'Connect Google Account' : 'Connect with OAuth'}
            </button>
          )}
        </div>
      ) : (
        /* Standard enable / disable toggle */
        <div className="flex items-center justify-between rounded-lg bg-muted/50 p-3">
          <span className="text-sm font-medium">Enabled</span>
          <MCPToggle enabled={server.state === 'enabled' || server.state === 'connected'} onChange={(val) => onToggle?.(server.id, val)} />
        </div>
      )}

      {/* API Keys / Secrets form */}
      {needsApiKeys && (
        <div className="space-y-3 rounded-lg border border-border p-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium">API Keys Required</p>
            <span className="flex items-center gap-1 rounded-full bg-green-500/10 px-2 py-0.5 text-[10px] font-medium text-green-600">
              <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
              GCP Secret Manager
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground">Keys are encrypted at rest via Google Cloud Secret Manager and never exposed after saving.</p>
          {server.env_keys.map((key) => (
            <div key={key} className="space-y-1">
              <label className="text-xs text-muted-foreground">{key}</label>
              <input
                type="password"
                placeholder={`Enter ${key}`}
                value={secrets[key] || ''}
                onChange={(e) => setSecrets((prev) => ({ ...prev, [key]: e.target.value }))}
                className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          ))}
          <div className="flex items-center gap-2">
            <button
              onClick={async () => {
                setSecretsLoading(true);
                try {
                  await saveSecrets(server.id, secrets);
                  setSecretsSaved(true);
                } finally {
                  setSecretsLoading(false);
                }
              }}
              disabled={secretsLoading || Object.values(secrets).every((v) => !v)}
              className="rounded-lg bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {secretsLoading ? 'Saving…' : 'Save Keys'}
            </button>
            {secretsSaved && <span className="text-xs text-green-500">✓ Keys saved</span>}
          </div>
        </div>
      )}

      {/* Transport info */}
      {server.transport && (
        <div>
          <p className="text-xs font-medium text-muted-foreground">Transport</p>
          <p className="text-sm">{server.transport}{server.url ? ` — ${server.url}` : ''}</p>
        </div>
      )}

      {/* Tools list */}
      <div>
        <h3 className="mb-2 text-sm font-medium">Tools ({server.tools?.length || server.tools_summary?.length || 0})</h3>
        {(server.tools?.length > 0 || server.tools_summary?.length > 0) ? (
          <ul className="space-y-1">
            {(server.tools || server.tools_summary || []).map((tool, i) => (
              <li key={i} className="rounded bg-muted/50 px-3 py-1.5 text-sm">
                <span className="font-mono text-xs">{typeof tool === 'string' ? tool : tool.name}</span>
                {tool.description && <p className="text-xs text-muted-foreground">{tool.description}</p>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">{isOAuth && !isConnected ? 'Connect to discover tools' : 'No tools listed'}</p>
        )}
      </div>
    </div>
  );
}
