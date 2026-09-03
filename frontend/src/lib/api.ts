export interface Repository {
  id: number;
  name: string;
  full_name: string;
  private: boolean;
  html_url: string;
}

export interface Branch {
  name: string;
  commit_sha: string;
  protected: boolean;
}

export interface GitTreeItem {
  path: string;
  type: 'blob' | 'tree';
  size?: number;
  sha: string;
}

export interface GitHubConnectionStatus {
  connected: boolean;
  github_user_id?: number;
  github_username?: string;
  created_at?: string;
}

export interface ReviewItem {
  id: string;
  idempotency_key: string;
  status: 'PROCESSING' | 'COMPLETED' | 'FAILED';
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  findings_count: number;
  files?: Array<{ id: string; file_path: string; status: string }>;
}

export interface FindingItem {
  id: string;
  file_path: string;
  line_number: number;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  category: 'BUG' | 'SECURITY' | 'PERFORMANCE' | 'MAINTAINABILITY';
  title: string;
  message: string;
  suggestion?: string | null;
  created_at: string;
}

export interface ReviewsListResponse {
  total: number;
  limit: number;
  offset: number;
  reviews: ReviewItem[];
}

export interface ReviewFindingsResponse {
  review_id: string;
  status: string;
  total_findings: number;
  findings: FindingItem[];
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000/api/v1';

export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('auth_token');
}

export function setAuthToken(token: string): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem('auth_token', token);
  }
}

export function removeAuthToken(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('auth_token');
  }
}

export function generateUUID(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    removeAuthToken();
    if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
      window.location.href = '/login';
    }
    throw new Error('Authentication required');
  }

  if (response.status === 409) {
    const errorData = await response.json().catch(() => ({ detail: 'Conflict error' }));
    throw new Error(errorData.detail || 'Idempotency key conflict: Payload differs from previous request.');
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `Request failed with status ${response.status}`);
  }

  return response.json();
}

export const api = {
  getGitHubStatus: () => request<GitHubConnectionStatus>('/github/status'),

  getGitHubAuthUrl: async () => {
    const res = await request<{ authorization_url?: string; auth_url?: string; state: string }>('/github/auth');
    return {
      auth_url: res.authorization_url || res.auth_url || '',
      state: res.state,
    };
  },

  githubCallback: (code: string, state: string) =>
    request<{
      status: string;
      github_user_id: string;
      access_token?: string;
      token_type?: string;
      user_id?: string;
    }>(`/github/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`),

  deleteGitHubConnection: () => request<{ status: string }>('/github/connection', { method: 'DELETE' }),

  getRepositories: () => request<Repository[]>('/github/repositories'),

  getBranches: (owner: string, repo: string) =>
    request<{ branches: Branch[] }>(`/github/repositories/${owner}/${repo}/branches`),

  getGitTree: (owner: string, repo: string, ref: string) =>
    request<{ tree: GitTreeItem[] }>(`/github/repositories/${owner}/${repo}/tree/${ref}`),

  createReview: (payload: { repository_id: string; ref: string; files: string[]; categories: string[] }) => {
    const idempotencyKey = generateUUID();
    return request<ReviewItem>('/reviews', {
      method: 'POST',
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify(payload),
    });
  },

  listReviews: (statusParam?: string, limit: number = 20, offset: number = 0) => {
    const params = new URLSearchParams();
    if (statusParam) params.append('status', statusParam);
    params.append('limit', limit.toString());
    params.append('offset', offset.toString());
    return request<ReviewsListResponse>(`/reviews?${params.toString()}`);
  },

  getReviewDetail: (reviewId: string) => request<ReviewItem>(`/reviews/${reviewId}`),

  getReviewFindings: (
    reviewId: string,
    params?: { file_path?: string; category?: string; severity?: string }
  ) => {
    const query = new URLSearchParams();
    if (params?.file_path) query.append('file_path', params.file_path);
    if (params?.category) query.append('category', params.category);
    if (params?.severity) query.append('severity', params.severity);
    return request<ReviewFindingsResponse>(`/reviews/${reviewId}/findings?${query.toString()}`);
  },
};
