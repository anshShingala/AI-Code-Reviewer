'use client';

import React, { useEffect, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { api, setAuthToken } from '@/lib/api';
import { Shield, RefreshCw, AlertCircle } from 'lucide-react';

function CallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get('code');
    const state = searchParams.get('state');

    if (!code || !state) {
      setError('Missing authorization code or OAuth state parameter.');
      return;
    }

    let isSubscribed = true;

    async function processCallback() {
      try {
        const data = await api.githubCallback(code!, state!);
        if (!isSubscribed) return;

        if (data.access_token) {
          setAuthToken(data.access_token);
          router.push('/');
        } else {
          throw new Error('Authentication succeeded but no application access token was returned.');
        }
      } catch (err: unknown) {
        if (!isSubscribed) return;
        setError(err instanceof Error ? err.message : 'GitHub authentication callback failed');
      }
    }

    processCallback();

    return () => {
      isSubscribed = false;
    };
  }, [searchParams, router]);

  if (error) {
    return (
      <div className="max-w-md mx-auto my-12 bg-white rounded-2xl border border-slate-200 p-8 shadow-sm text-center space-y-4">
        <div className="bg-rose-100 w-12 h-12 rounded-xl text-rose-600 flex items-center justify-center mx-auto">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h2 className="text-xl font-bold text-slate-900">Authentication Failed</h2>
        <p className="text-sm text-rose-600 bg-rose-50 p-3 rounded-lg border border-rose-200">{error}</p>
        <button
          onClick={() => router.push('/login')}
          className="w-full bg-slate-900 hover:bg-slate-800 text-white font-medium py-2.5 px-4 rounded-lg text-sm transition"
        >
          Return to Sign In
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto my-16 bg-white rounded-2xl border border-slate-200 p-8 shadow-sm text-center space-y-4">
      <div className="bg-sky-600 w-12 h-12 rounded-xl text-white flex items-center justify-center mx-auto">
        <Shield className="w-6 h-6 animate-pulse" />
      </div>
      <h2 className="text-xl font-bold text-slate-900">Completing Sign In</h2>
      <div className="flex items-center justify-center space-x-2 text-slate-500 text-sm">
        <RefreshCw className="w-4 h-4 animate-spin" />
        <span>Authenticating with GitHub...</span>
      </div>
    </div>
  );
}

export default function GitHubCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-md mx-auto my-16 text-center text-slate-500 text-sm">
          Loading authentication session...
        </div>
      }
    >
      <CallbackContent />
    </Suspense>
  );
}
