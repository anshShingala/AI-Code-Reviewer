'use client';

import React, { useState } from 'react';
import GitHubConnect from '@/components/GitHubConnect';
import RepoSelector from '@/components/RepoSelector';
import ReviewForm from '@/components/ReviewForm';
import ReviewHistory from '@/components/ReviewHistory';
import { ReviewItem } from '@/lib/api';

export default function HomePage() {
  const [isConnected, setIsConnected] = useState(false);
  const [repoId, setRepoId] = useState('');
  const [refName, setRefName] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);

  const handleSelection = (repo: string, ref: string, files: string[]) => {
    setRepoId(repo);
    setRefName(ref);
    setSelectedFiles(files);
  };

  const handleReviewCreated = (review: ReviewItem) => {
    setRefreshKey((prev) => prev + 1);
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">AI Code Review Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">
          Perform intelligent automated code reviews on GitHub repository Pull Requests.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
          <GitHubConnect onStatusChange={setIsConnected} />
          <RepoSelector isConnected={isConnected} onSelect={handleSelection} />
          <ReviewForm
            repositoryId={repoId}
            refName={refName}
            selectedFiles={selectedFiles}
            onReviewCreated={handleReviewCreated}
          />
        </div>

        <div className="lg:col-span-1">
          <ReviewHistory refreshKey={refreshKey} />
        </div>
      </div>
    </div>
  );
}
