'use client';

import React, { useEffect, useState } from 'react';
import { api, Branch, GitTreeItem, Repository } from '@/lib/api';
import { FolderGit2, GitBranch, FileCode, CheckSquare, Square, RefreshCw, AlertCircle } from 'lucide-react';

interface RepoSelectorProps {
  isConnected: boolean;
  onSelect: (repoId: string, ref: string, selectedFiles: string[]) => void;
}

export default function RepoSelector({ isConnected, onSelect }: RepoSelectorProps) {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>('');
  const [branches, setBranches] = useState<Branch[]>([]);
  const [selectedBranch, setSelectedBranch] = useState<string>('');
  const [treeItems, setTreeItems] = useState<GitTreeItem[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);

  const [loadingRepos, setLoadingRepos] = useState(false);
  const [loadingBranches, setLoadingBranches] = useState(false);
  const [loadingTree, setLoadingTree] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isConnected) {
      fetchRepositories();
    } else {
      setRepos([]);
      setSelectedRepo('');
      setBranches([]);
      setSelectedBranch('');
      setTreeItems([]);
      setSelectedFiles([]);
    }
  }, [isConnected]);

  const fetchRepositories = async () => {
    setLoadingRepos(true);
    setError(null);
    try {
      const data = await api.getRepositories();
      setRepos(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load repositories');
    } finally {
      setLoadingRepos(false);
    }
  };

  const handleRepoChange = async (repoFullName: string) => {
    setSelectedRepo(repoFullName);
    setSelectedBranch('');
    setBranches([]);
    setTreeItems([]);
    setSelectedFiles([]);
    if (!repoFullName) return;

    const [owner, repo] = repoFullName.split('/');
    setLoadingBranches(true);
    setError(null);
    try {
      const data = await api.getBranches(owner, repo);
      setBranches(data.branches || []);
      if (data.branches && data.branches.length > 0) {
        const defaultBranch = data.branches.find((b) => b.name === 'main' || b.name === 'master') || data.branches[0];
        handleBranchChange(repoFullName, defaultBranch.name);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load branches');
    } finally {
      setLoadingBranches(false);
    }
  };

  const handleBranchChange = async (repoFullName: string, branchName: string) => {
    setSelectedBranch(branchName);
    setTreeItems([]);
    setSelectedFiles([]);
    if (!repoFullName || !branchName) return;

    const [owner, repo] = repoFullName.split('/');
    setLoadingTree(true);
    setError(null);
    try {
      const data = await api.getGitTree(owner, repo, branchName);
      const filesOnly = (data.tree || []).filter((item) => item.type === 'blob');
      setTreeItems(filesOnly);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load file tree');
    } finally {
      setLoadingTree(false);
    }
  };

  const toggleFile = (path: string) => {
    const updated = selectedFiles.includes(path)
      ? selectedFiles.filter((p) => p !== path)
      : [...selectedFiles, path];
    setSelectedFiles(updated);
    if (selectedRepo && selectedBranch) {
      onSelect(selectedRepo, selectedBranch, updated);
    }
  };

  const toggleAll = () => {
    if (selectedFiles.length === treeItems.length) {
      setSelectedFiles([]);
      onSelect(selectedRepo, selectedBranch, []);
    } else {
      const allPaths = treeItems.map((item) => item.path);
      setSelectedFiles(allPaths);
      onSelect(selectedRepo, selectedBranch, allPaths);
    }
  };

  if (!isConnected) {
    return (
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center text-slate-500">
        <FolderGit2 className="w-12 h-12 mx-auto text-slate-300 mb-3" />
        <p className="font-medium">Connect your GitHub account above to select repositories.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-6">
      <h3 className="font-semibold text-slate-900 text-lg flex items-center space-x-2">
        <FolderGit2 className="w-5 h-5 text-sky-600" />
        <span>Target Repository & File Selection</span>
      </h3>

      {error && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-center space-x-2 text-rose-700 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Repository Dropdown */}
        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-2">Repository</label>
          <div className="relative">
            <select
              value={selectedRepo}
              onChange={(e) => handleRepoChange(e.target.value)}
              disabled={loadingRepos}
              className="w-full bg-slate-50 border border-slate-300 text-slate-900 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-sky-500 focus:bg-white transition"
            >
              <option value="">Select a repository...</option>
              {repos.map((r) => (
                <option key={r.id} value={r.full_name}>
                  {r.full_name}
                </option>
              ))}
            </select>
            {loadingRepos && (
              <RefreshCw className="w-4 h-4 animate-spin absolute right-3 top-3 text-slate-400" />
            )}
          </div>
        </div>

        {/* Branch Dropdown */}
        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase mb-2 flex items-center space-x-1">
            <GitBranch className="w-3.5 h-3.5 text-slate-500" />
            <span>Branch / Ref</span>
          </label>
          <div className="relative">
            <select
              value={selectedBranch}
              onChange={(e) => handleBranchChange(selectedRepo, e.target.value)}
              disabled={!selectedRepo || loadingBranches}
              className="w-full bg-slate-50 border border-slate-300 text-slate-900 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-sky-500 focus:bg-white transition disabled:opacity-50"
            >
              <option value="">Select branch...</option>
              {branches.map((b) => (
                <option key={b.name} value={b.name}>
                  {b.name}
                </option>
              ))}
            </select>
            {loadingBranches && (
              <RefreshCw className="w-4 h-4 animate-spin absolute right-3 top-3 text-slate-400" />
            )}
          </div>
        </div>
      </div>

      {/* File Tree Checklist */}
      {selectedRepo && selectedBranch && (
        <div className="border border-slate-200 rounded-lg overflow-hidden bg-slate-50">
          <div className="bg-slate-100 px-4 py-2.5 border-b border-slate-200 flex items-center justify-between">
            <div className="flex items-center space-x-2 text-xs font-semibold text-slate-700 uppercase">
              <FileCode className="w-4 h-4 text-sky-600" />
              <span>Select Target Files ({selectedFiles.length} of {treeItems.length} selected)</span>
            </div>
            {treeItems.length > 0 && (
              <button
                onClick={toggleAll}
                className="text-xs text-sky-600 hover:text-sky-700 font-medium transition"
              >
                {selectedFiles.length === treeItems.length ? 'Deselect All' : 'Select All'}
              </button>
            )}
          </div>

          <div className="max-h-60 overflow-y-auto divide-y divide-slate-200 bg-white">
            {loadingTree ? (
              <div className="p-6 text-center text-slate-400 text-sm flex items-center justify-center space-x-2">
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Loading Git tree...</span>
              </div>
            ) : treeItems.length === 0 ? (
              <div className="p-6 text-center text-slate-400 text-sm">No files found in branch</div>
            ) : (
              treeItems.map((item) => {
                const isSelected = selectedFiles.includes(item.path);
                return (
                  <div
                    key={item.path}
                    onClick={() => toggleFile(item.path)}
                    className="px-4 py-2 flex items-center justify-between hover:bg-sky-50/50 cursor-pointer transition text-sm"
                  >
                    <div className="flex items-center space-x-3 truncate">
                      {isSelected ? (
                        <CheckSquare className="w-4 h-4 text-sky-600 flex-shrink-0" />
                      ) : (
                        <Square className="w-4 h-4 text-slate-400 flex-shrink-0" />
                      )}
                      <span className={`truncate font-mono text-xs ${isSelected ? 'text-slate-900 font-semibold' : 'text-slate-600'}`}>
                        {item.path}
                      </span>
                    </div>
                    {item.size && (
                      <span className="text-xs text-slate-400 font-mono flex-shrink-0 ml-2">
                        {(item.size / 1024).toFixed(1)} KB
                      </span>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
