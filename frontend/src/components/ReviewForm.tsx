'use client';

import React, { useState } from 'react';
import { api, ReviewItem } from '@/lib/api';
import { Play, CheckCircle2, AlertTriangle, RefreshCw, Sliders } from 'lucide-react';

interface ReviewFormProps {
  repositoryId: string;
  refName: string;
  selectedFiles: string[];
  onReviewCreated: (review: ReviewItem) => void;
}

const CATEGORIES = [
  { id: 'BUG', label: 'Bugs & Logical Flaws', color: 'text-amber-600' },
  { id: 'SECURITY', label: 'Security Vulnerabilities', color: 'text-rose-600' },
  { id: 'PERFORMANCE', label: 'Performance Bottlenecks', color: 'text-purple-600' },
  { id: 'MAINTAINABILITY', label: 'Code Quality & Maintainability', color: 'text-sky-600' },
];

export default function ReviewForm({ repositoryId, refName, selectedFiles, onReviewCreated }: ReviewFormProps) {
  const [selectedCategories, setSelectedCategories] = useState<string[]>(['BUG', 'SECURITY', 'PERFORMANCE', 'MAINTAINABILITY']);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [infoMsg, setInfoMsg] = useState<string | null>(null);

  const toggleCategory = (id: string) => {
    if (selectedCategories.includes(id)) {
      if (selectedCategories.length === 1) return; // Must select at least 1
      setSelectedCategories(selectedCategories.filter((c) => c !== id));
    } else {
      setSelectedCategories([...selectedCategories, id]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repositoryId || !refName || selectedFiles.length === 0) {
      setError('Please select a repository, branch, and at least one file.');
      return;
    }

    setLoading(true);
    setError(null);
    setInfoMsg(null);

    try {
      const result = await api.createReview({
        repository_id: repositoryId,
        ref: refName,
        files: selectedFiles,
        categories: selectedCategories,
      });

      onReviewCreated(result);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '';
      if (msg.includes('Idempotency key conflict')) {
        setError('409 Conflict: Idempotency key reuse with conflicting request payload.');
      } else {
        setError(msg || 'Failed to submit code review request.');
      }
    } finally {
      setLoading(false);
    }
  };

  const isFormValid = repositoryId && refName && selectedFiles.length > 0 && selectedCategories.length > 0;

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-6">
      <h3 className="font-semibold text-slate-900 text-lg flex items-center space-x-2">
        <Sliders className="w-5 h-5 text-sky-600" />
        <span>Review Categories & Execution</span>
      </h3>

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-lg flex items-center space-x-3 text-rose-700 text-sm">
          <AlertTriangle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {infoMsg && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-center space-x-3 text-amber-700 text-sm">
          <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
          <span>{infoMsg}</span>
        </div>
      )}

      <div>
        <label className="block text-xs font-semibold text-slate-600 uppercase mb-3">Review Categories</label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {CATEGORIES.map((cat) => {
            const isChecked = selectedCategories.includes(cat.id);
            return (
              <div
                key={cat.id}
                onClick={() => toggleCategory(cat.id)}
                className={`p-3 rounded-lg border cursor-pointer transition flex items-center justify-between ${
                  isChecked
                    ? 'border-sky-500 bg-sky-50/50 text-slate-900 font-semibold'
                    : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300'
                }`}
              >
                <span className="text-sm">{cat.label}</span>
                <span className={`text-xs font-mono px-2 py-0.5 rounded ${isChecked ? 'bg-sky-200 text-sky-800' : 'bg-slate-200 text-slate-600'}`}>
                  {cat.id}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <button
        type="submit"
        disabled={!isFormValid || loading}
        className="w-full bg-sky-600 hover:bg-sky-500 text-white font-semibold py-3 px-4 rounded-lg transition shadow-sm flex items-center justify-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? (
          <>
            <RefreshCw className="w-5 h-5 animate-spin" />
            <span>Initiating AI Code Review...</span>
          </>
        ) : (
          <>
            <Play className="w-5 h-5 fill-current" />
            <span>Submit Review Request ({selectedFiles.length} files selected)</span>
          </>
        )}
      </button>
    </form>
  );
}
