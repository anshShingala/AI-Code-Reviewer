'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, setAuthToken } from '@/lib/api';
import { Shield, Key, ArrowRight, Github, RefreshCw } from 'lucide-react';

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [token, setTokenInput] = useState('');
  const [showDevInput, setShowDevInput] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  const handleGitHubLogin = async () => {
    setLoading(true);
    setError(null);
    try {
      const { auth_url } = await api.getGitHubAuthUrl();
      if (auth_url) {
        window.location.href = auth_url;
      } else {
        throw new Error('Failed to retrieve GitHub authentication URL.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to initiate GitHub authentication');
      setLoading(false);
    }
  };

  const handleManualTokenLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim()) {
      setError('Please enter a valid JWT token.');
      return;
    }
    setAuthToken(token.trim());
    router.push('/');
  };

  return (
    <div className="max-w-md mx-auto my-12 bg-white rounded-2xl border border-slate-200 p-8 shadow-sm space-y-6">
      <div className="text-center space-y-2">
        <div className="bg-sky-600 w-12 h-12 rounded-xl text-white flex items-center justify-center mx-auto">
          <Shield className="w-6 h-6" />
        </div>
        <h2 className="text-2xl font-bold text-slate-900">Welcome Back</h2>
        <p className="text-sm text-slate-500">Sign in with your GitHub account to access AI Code Reviewer</p>
      </div>

      {error && <div className="p-3 bg-rose-50 border border-rose-200 text-rose-700 text-sm rounded-lg">{error}</div>}

      <div className="space-y-4">
        <button
          onClick={handleGitHubLogin}
          disabled={loading}
          className="w-full bg-slate-900 hover:bg-slate-800 text-white font-semibold py-3 px-4 rounded-xl transition flex items-center justify-center space-x-3 shadow-sm disabled:opacity-50"
        >
          {loading ? (
            <RefreshCw className="w-5 h-5 animate-spin" />
          ) : (
            <Github className="w-5 h-5 text-white" />
          )}
          <span>{loading ? 'Connecting to GitHub...' : 'Continue with GitHub'}</span>
        </button>

        <div className="pt-4 border-t border-slate-100 text-center">
          <button
            type="button"
            onClick={() => setShowDevInput(!showDevInput)}
            className="text-xs font-medium text-slate-400 hover:text-slate-600 transition flex items-center justify-center mx-auto space-x-1"
          >
            <Key className="w-3.5 h-3.5" />
            <span>{showDevInput ? 'Hide Developer Token Input' : 'Developer Mode (Manual JWT Entry)'}</span>
          </button>
        </div>

        {showDevInput && (
          <form onSubmit={handleManualTokenLogin} className="space-y-3 pt-2">
            <div>
              <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">Developer Bearer JWT</label>
              <div className="relative">
                <input
                  type="text"
                  value={token}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="Paste Bearer JWT token..."
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs font-mono focus:ring-2 focus:ring-sky-500 focus:bg-white"
                />
              </div>
            </div>
            <button
              type="submit"
              className="w-full bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium py-2 px-3 rounded-lg text-xs transition flex items-center justify-center space-x-1"
            >
              <span>Use JWT Token</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
