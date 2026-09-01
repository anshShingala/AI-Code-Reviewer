'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { setAuthToken } from '@/lib/api';
import { Key, Shield, ArrowRight } from 'lucide-react';

export default function LoginPage() {
  const [token, setTokenInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  const handleLogin = (e: React.FormEvent) => {
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
        <p className="text-sm text-slate-500">Authenticate session to access AI Code Reviewer</p>
      </div>

      {error && <div className="p-3 bg-rose-50 text-rose-700 text-sm rounded-lg">{error}</div>}

      <form onSubmit={handleLogin} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-2">JWT Access Token</label>
          <div className="relative">
            <input
              type="text"
              value={token}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="Paste Bearer JWT token..."
              className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2.5 pl-10 text-sm font-mono focus:ring-2 focus:ring-sky-500 focus:bg-white"
            />
            <Key className="w-4 h-4 text-slate-400 absolute left-3 top-3.5" />
          </div>
        </div>

        <button
          type="submit"
          className="w-full bg-sky-600 hover:bg-sky-500 text-white font-semibold py-2.5 px-4 rounded-lg transition flex items-center justify-center space-x-2"
        >
          <span>Continue to Dashboard</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
}
