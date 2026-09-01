'use client';

import React, { useEffect, useState } from 'react';
import { api, GitHubConnectionStatus } from '@/lib/api';
import { Github, CheckCircle2, AlertCircle, RefreshCw, Trash2 } from 'lucide-react';

export default function GitHubConnect({ onStatusChange }: { onStatusChange?: (connected: boolean) => void }) {
  const [status, setStatus] = useState<GitHubConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getGitHubStatus();
      setStatus(data);
      if (onStatusChange) onStatusChange(data.connected);
    } catch (err: any) {
      setError(err.message || 'Failed to check GitHub status');
      if (onStatusChange) onStatusChange(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleConnect = async () => {
    try {
      const { auth_url } = await api.getGitHubAuthUrl();
      window.location.href = auth_url;
    } catch (err: any) {
      setError(err.message || 'Failed to initiate OAuth flow');
    }
  };

  const handleDisconnect = async () => {
    if (!confirm('Are you sure you want to disconnect your GitHub account?')) return;
    try {
      await api.deleteGitHubConnection();
      await fetchStatus();
    } catch (err: any) {
      setError(err.message || 'Failed to disconnect account');
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-3 bg-slate-100 rounded-lg text-slate-800">
            <Github className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-900">GitHub Connection</h3>
            <p className="text-sm text-slate-500">Connect your account to analyze repositories</p>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center space-x-2 text-slate-400 text-sm">
            <RefreshCw className="w-4 h-4 animate-spin" />
            <span>Checking...</span>
          </div>
        ) : status?.connected ? (
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2 text-emerald-600 bg-emerald-50 px-3 py-1.5 rounded-full text-xs font-semibold border border-emerald-200">
              <CheckCircle2 className="w-4 h-4" />
              <span>Connected as @{status.github_username}</span>
            </div>
            <button
              onClick={handleDisconnect}
              className="text-rose-600 hover:text-rose-700 hover:bg-rose-50 p-2 rounded-lg text-xs font-medium transition flex items-center space-x-1"
            >
              <Trash2 className="w-4 h-4" />
              <span>Disconnect</span>
            </button>
          </div>
        ) : (
          <button
            onClick={handleConnect}
            className="flex items-center space-x-2 bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 rounded-lg text-sm font-medium transition shadow-sm"
          >
            <Github className="w-4 h-4" />
            <span>Connect GitHub</span>
          </button>
        )}
      </div>

      {error && (
        <div className="mt-4 p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-center space-x-2 text-rose-700 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
