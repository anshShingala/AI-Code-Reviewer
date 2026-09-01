'use client';

import React, { useEffect, useState } from 'react';
import { api, FindingItem, ReviewItem } from '@/lib/api';
import { ShieldAlert, Filter, FileText, Bug, AlertTriangle, Zap, CheckCircle2, ChevronDown } from 'lucide-react';

export default function FindingsDashboard({ review }: { review: ReviewItem }) {
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [totalFindings, setTotalFindings] = useState(0);
  const [fileFilter, setFileFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFindings = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getReviewFindings(review.id, {
        file_path: fileFilter || undefined,
        category: categoryFilter || undefined,
        severity: severityFilter || undefined,
      });
      setFindings(data.findings || []);
      setTotalFindings(data.total_findings || 0);
    } catch (err: any) {
      setError(err.message || 'Failed to load findings');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFindings();
  }, [review.id, fileFilter, categoryFilter, severityFilter]);

  const renderSeverityBadge = (sev: string) => {
    switch (sev) {
      case 'CRITICAL':
        return <span className="bg-rose-100 text-rose-800 border border-rose-300 font-bold px-2 py-0.5 rounded text-xs">CRITICAL</span>;
      case 'HIGH':
        return <span className="bg-orange-100 text-orange-800 border border-orange-300 font-bold px-2 py-0.5 rounded text-xs">HIGH</span>;
      case 'MEDIUM':
        return <span className="bg-amber-100 text-amber-800 border border-amber-300 font-semibold px-2 py-0.5 rounded text-xs">MEDIUM</span>;
      default:
        return <span className="bg-sky-100 text-sky-800 border border-sky-300 font-semibold px-2 py-0.5 rounded text-xs">LOW</span>;
    }
  };

  const renderCategoryIcon = (cat: string) => {
    switch (cat) {
      case 'SECURITY':
        return <ShieldAlert className="w-4 h-4 text-rose-600" />;
      case 'BUG':
        return <Bug className="w-4 h-4 text-amber-600" />;
      case 'PERFORMANCE':
        return <Zap className="w-4 h-4 text-purple-600" />;
      default:
        return <FileText className="w-4 h-4 text-sky-600" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Review Summary Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-3">
              <h2 className="text-xl font-bold text-slate-900">Review {review.id.substring(0, 8)}...</h2>
              <span className={`px-3 py-1 rounded-full text-xs font-bold border ${
                review.status === 'COMPLETED' ? 'bg-emerald-50 text-emerald-700 border-emerald-300' :
                review.status === 'FAILED' ? 'bg-rose-50 text-rose-700 border-rose-300' :
                'bg-amber-50 text-amber-700 border-amber-300'
              }`}>
                {review.status}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">Created: {new Date(review.created_at).toLocaleString()}</p>
          </div>

          <div className="flex items-center space-x-6 text-sm">
            <div className="text-center">
              <span className="block text-xs text-slate-400 font-medium">Target Files</span>
              <span className="font-bold text-slate-800">{review.files?.length || 0}</span>
            </div>
            <div className="text-center">
              <span className="block text-xs text-slate-400 font-medium">Total Findings</span>
              <span className="font-bold text-slate-800">{review.findings_count}</span>
            </div>
          </div>
        </div>

        {review.error_message && (
          <div className="mt-4 p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-700 text-sm flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>{review.error_message}</span>
          </div>
        )}
      </div>

      {/* Filter Controls Bar */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center space-x-2 text-sm font-semibold text-slate-700">
          <Filter className="w-4 h-4 text-sky-600" />
          <span>Filter Findings</span>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* File Filter */}
          <select
            value={fileFilter}
            onChange={(e) => setFileFilter(e.target.value)}
            className="bg-slate-50 border border-slate-300 text-slate-700 text-xs rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-sky-500"
          >
            <option value="">All Files</option>
            {review.files?.map((f) => (
              <option key={f.id} value={f.file_path}>
                {f.file_path}
              </option>
            ))}
          </select>

          {/* Category Filter */}
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="bg-slate-50 border border-slate-300 text-slate-700 text-xs rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-sky-500"
          >
            <option value="">All Categories</option>
            <option value="BUG">BUG</option>
            <option value="SECURITY">SECURITY</option>
            <option value="PERFORMANCE">PERFORMANCE</option>
            <option value="MAINTAINABILITY">MAINTAINABILITY</option>
          </select>

          {/* Severity Filter */}
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="bg-slate-50 border border-slate-300 text-slate-700 text-xs rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-sky-500"
          >
            <option value="">All Severities</option>
            <option value="CRITICAL">CRITICAL</option>
            <option value="HIGH">HIGH</option>
            <option value="MEDIUM">MEDIUM</option>
            <option value="LOW">LOW</option>
          </select>
        </div>
      </div>

      {/* Findings List */}
      <div className="space-y-4">
        {loading ? (
          <div className="p-8 text-center text-slate-400 bg-white rounded-xl border border-slate-200">
            Loading findings...
          </div>
        ) : findings.length === 0 ? (
          <div className="p-12 text-center text-slate-500 bg-white rounded-xl border border-slate-200">
            <CheckCircle2 className="w-12 h-12 mx-auto text-emerald-500 mb-3" />
            <h4 className="font-semibold text-slate-800 text-lg">No Findings Identified</h4>
            <p className="text-sm text-slate-500 mt-1">No issues match the selected filters for this review.</p>
          </div>
        ) : (
          findings.map((f) => (
            <div key={f.id} className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                <div className="flex items-center space-x-2">
                  {renderCategoryIcon(f.category)}
                  <span className="font-mono text-xs font-bold text-slate-800">{f.file_path}:{f.line_number}</span>
                  <span className="text-slate-300">|</span>
                  <span className="text-xs font-semibold text-slate-600">{f.category}</span>
                </div>
                {renderSeverityBadge(f.severity)}
              </div>

              <h4 className="font-bold text-slate-900 text-base">{f.title}</h4>
              <p className="text-sm text-slate-600 leading-relaxed">{f.message}</p>

              {f.suggestion && (
                <div className="mt-3 p-3 bg-slate-900 text-slate-200 rounded-lg text-xs font-mono border border-slate-800">
                  <span className="block text-sky-400 font-bold mb-1 font-sans text-xs">Suggested Fix:</span>
                  <pre className="whitespace-pre-wrap">{f.suggestion}</pre>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
