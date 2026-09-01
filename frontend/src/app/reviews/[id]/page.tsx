'use client';

import React, { useEffect, useState, useRef } from 'react';
import Link from 'next/link';
import { api, ReviewItem } from '@/lib/api';
import FindingsDashboard from '@/components/FindingsDashboard';
import { ArrowLeft, RefreshCw, AlertCircle, Clock, XCircle } from 'lucide-react';

export default function ReviewDetailPage({ params }: { params: { id: string } }) {
  const [review, setReview] = useState<ReviewItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const startTimeRef = useRef<number>(Date.now());

  const fetchReview = async (isManual = false) => {
    if (isManual) setLoading(true);
    setError(null);
    try {
      const data = await api.getReviewDetail(params.id);
      setReview(data);
      return data;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load review details');
      return null;
    } finally {
      if (isManual) setLoading(false);
    }
  };

  useEffect(() => {
    let isSubscribed = true;
    let timerId: NodeJS.Timeout | null = null;
    startTimeRef.current = Date.now();

    const poll = async () => {
      try {
        const data = await api.getReviewDetail(params.id);
        if (!isSubscribed) return;

        setReview(data);
        setLoading(false);

        // Stop polling if terminal state reached
        if (data.status !== 'PROCESSING') {
          if (timerId) clearInterval(timerId);
          return;
        }

        // Stop polling if 10-minute safety limit exceeded (600,000 ms)
        if (Date.now() - startTimeRef.current > 600000) {
          setError('Polling timeout: Review processing is taking longer than expected. Please refresh manually.');
          if (timerId) clearInterval(timerId);
          return;
        }
      } catch (err: unknown) {
        if (!isSubscribed) return;
        setError(err instanceof Error ? err.message : 'Failed to poll review status');
        setLoading(false);
        if (timerId) clearInterval(timerId);
      }
    };

    // Initial load
    poll();

    // Start 3-second polling interval
    timerId = setInterval(poll, 3000);

    return () => {
      isSubscribed = false;
      if (timerId) clearInterval(timerId);
    };
  }, [params.id]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Link
          href="/"
          className="inline-flex items-center space-x-2 text-sm font-semibold text-slate-600 hover:text-slate-900 transition"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Dashboard</span>
        </Link>

        <button
          onClick={() => fetchReview(true)}
          className="p-2 bg-white border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50 transition shadow-sm"
          title="Refresh Review"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading ? (
        <div className="p-12 text-center text-slate-400 bg-white rounded-xl border border-slate-200">
          Loading review details...
        </div>
      ) : error ? (
        <div className="p-6 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-sm flex items-center space-x-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      ) : review ? (
        review.status === 'PROCESSING' ? (
          <div className="bg-white rounded-xl border border-amber-200 p-8 shadow-sm text-center space-y-4">
            <div className="inline-flex items-center justify-center w-12 h-12 bg-amber-100 rounded-full text-amber-600">
              <RefreshCw className="w-6 h-6 animate-spin" />
            </div>
            <div>
              <div className="inline-flex items-center space-x-2 bg-amber-50 text-amber-800 border border-amber-200 text-xs font-semibold px-3 py-1 rounded-full mb-2">
                <Clock className="w-3.5 h-3.5 animate-pulse" />
                <span>PROCESSING IN BACKGROUND</span>
              </div>
              <h2 className="text-xl font-bold text-slate-900">AI Review Engine Processing</h2>
              <p className="text-sm text-slate-500 max-w-md mx-auto mt-1">
                Gemini AI is currently analyzing source code files for bugs, security vulnerabilities, performance bottlenecks, and maintainability issues.
              </p>
            </div>
            <div className="pt-2 text-xs text-slate-400 font-mono">
              Review ID: {review.id} • Created: {new Date(review.created_at).toLocaleTimeString()}
            </div>
          </div>
        ) : review.status === 'FAILED' ? (
          <div className="bg-white rounded-xl border border-rose-200 p-8 shadow-sm space-y-4">
            <div className="flex items-center space-x-3 text-rose-700">
              <XCircle className="w-6 h-6 flex-shrink-0" />
              <h2 className="text-lg font-bold">Review Execution Failed</h2>
            </div>
            <p className="text-sm text-slate-600 bg-rose-50 p-4 rounded-lg border border-rose-100 font-mono text-xs">
              {review.error_message || 'An unexpected error occurred during background execution.'}
            </p>
            <div className="pt-2 flex justify-end">
              <button
                onClick={() => fetchReview(true)}
                className="px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-semibold hover:bg-slate-800 transition"
              >
                Retry Fetching Detail
              </button>
            </div>
          </div>
        ) : (
          <FindingsDashboard review={review} />
        )
      ) : null}
    </div>
  );
}
