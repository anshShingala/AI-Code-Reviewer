'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { api, ReviewItem } from '@/lib/api';
import { History, CheckCircle2, Clock, XCircle, ChevronLeft, ChevronRight, RefreshCw, Eye } from 'lucide-react';

export default function ReviewHistory({ refreshKey }: { refreshKey?: number }) {
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [offset, setOffset] = useState(0);
  const limit = 10;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchReviews = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listReviews(statusFilter || undefined, limit, offset);
      setReviews(data.reviews || []);
      setTotal(data.total || 0);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load review history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReviews();
  }, [statusFilter, offset, refreshKey]);

  useEffect(() => {
    let isSubscribed = true;
    let timerId: NodeJS.Timeout | null = null;

    const hasProcessing = reviews.some((r) => r.status === 'PROCESSING');
    if (hasProcessing) {
      timerId = setInterval(async () => {
        try {
          const data = await api.listReviews(statusFilter || undefined, limit, offset);
          if (isSubscribed) {
            setReviews(data.reviews || []);
            setTotal(data.total || 0);
          }
        } catch {
          // Ignore background polling errors
        }
      }, 5000);
    }

    return () => {
      isSubscribed = false;
      if (timerId) clearInterval(timerId);
    };
  }, [reviews, statusFilter, limit, offset]);

  const handleNext = () => {
    if (offset + limit < total) {
      setOffset(offset + limit);
    }
  };

  const handlePrev = () => {
    if (offset >= limit) {
      setOffset(offset - limit);
    }
  };

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
            COMPLETED
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-200">
            <XCircle className="w-3.5 h-3.5 mr-1" />
            FAILED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200">
            <Clock className="w-3.5 h-3.5 mr-1 animate-pulse" />
            PROCESSING
          </span>
        );
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-slate-900 text-lg flex items-center space-x-2">
          <History className="w-5 h-5 text-sky-600" />
          <span>Review History ({total})</span>
        </h3>

        <div className="flex items-center space-x-3">
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setOffset(0);
            }}
            className="bg-slate-50 border border-slate-300 text-slate-700 text-xs rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-sky-500"
          >
            <option value="">All Statuses</option>
            <option value="PROCESSING">PROCESSING</option>
            <option value="COMPLETED">COMPLETED</option>
            <option value="FAILED">FAILED</option>
          </select>

          <button
            onClick={fetchReviews}
            className="p-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg transition"
            title="Refresh history"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {error && <div className="p-3 bg-rose-50 text-rose-700 text-sm rounded-lg">{error}</div>}

      <div className="border border-slate-200 rounded-lg overflow-hidden">
        <table className="w-full text-left text-sm text-slate-600">
          <thead className="bg-slate-50 text-xs text-slate-500 uppercase font-semibold border-b border-slate-200">
            <tr>
              <th className="px-4 py-3">Review ID</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Findings</th>
              <th className="px-4 py-3">Created At</th>
              <th className="px-4 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 bg-white">
            {loading && reviews.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                  Loading review history...
                </td>
              </tr>
            ) : reviews.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                  No review records found.
                </td>
              </tr>
            ) : (
              reviews.map((r) => (
                <tr key={r.id} className="hover:bg-slate-50 transition">
                  <td className="px-4 py-3 font-mono text-xs font-semibold text-slate-900">
                    {r.id.substring(0, 8)}...
                  </td>
                  <td className="px-4 py-3">{renderStatusBadge(r.status)}</td>
                  <td className="px-4 py-3 font-medium text-slate-900">{r.findings_count}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {new Date(r.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/reviews/${r.id}`}
                      className="inline-flex items-center space-x-1 text-sky-600 hover:text-sky-700 font-medium text-xs bg-sky-50 px-2.5 py-1 rounded-md border border-sky-200 transition"
                    >
                      <Eye className="w-3.5 h-3.5" />
                      <span>View</span>
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="flex items-center justify-between text-xs text-slate-500 pt-2">
        <span>
          Showing {total === 0 ? 0 : offset + 1} to {Math.min(offset + limit, total)} of {total} reviews
        </span>
        <div className="flex items-center space-x-2">
          <button
            onClick={handlePrev}
            disabled={offset === 0}
            className="p-1.5 rounded-md border border-slate-300 text-slate-600 hover:bg-slate-100 disabled:opacity-40"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            onClick={handleNext}
            disabled={offset + limit >= total}
            className="p-1.5 rounded-md border border-slate-300 text-slate-600 hover:bg-slate-100 disabled:opacity-40"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
