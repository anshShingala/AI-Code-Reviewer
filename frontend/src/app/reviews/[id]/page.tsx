'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { api, ReviewItem } from '@/lib/api';
import FindingsDashboard from '@/components/FindingsDashboard';
import { ArrowLeft, RefreshCw, AlertCircle } from 'lucide-react';

export default function ReviewDetailPage({ params }: { params: { id: string } }) {
  const [review, setReview] = useState<ReviewItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchReview = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getReviewDetail(params.id);
      setReview(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load review details');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReview();
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
          onClick={fetchReview}
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
        <FindingsDashboard review={review} />
      ) : null}
    </div>
  );
}
