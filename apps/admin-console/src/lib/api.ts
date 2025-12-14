import axios from 'axios';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use((config) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // 暂时禁用 401 自动跳转，避免跳到不存在的 /login 页面
    // TODO: 后续需要实现登录页面或改用代理路由
    // if (error.response?.status === 401) {
    //   if (typeof window !== 'undefined') {
    //     localStorage.removeItem('token');
    //     window.location.href = '/login';
    //   }
    // }
    return Promise.reject(error);
  }
);

// Sites API
export const sitesApi = {
  list: () => api.get('/sites'),
  get: (id: string) => api.get(`/sites/${id}`),
  create: (data: any) => api.post('/sites', data),
  update: (id: string, data: any) => api.patch(`/sites/${id}`, data),
  delete: (id: string) => api.delete(`/sites/${id}`),
};

// NPCs API
export const npcsApi = {
  list: (params?: { site_id?: string; npc_type?: string }) =>
    api.get('/npcs', { params }),
  get: (id: string) => api.get(`/npcs/${id}`),
  create: (data: any) => api.post('/npcs', data),
  update: (id: string, data: any) => api.patch(`/npcs/${id}`, data),
  delete: (id: string) => api.delete(`/npcs/${id}`),
};

// Scenes API
export const scenesApi = {
  list: (params?: { site_id?: string }) => api.get('/scenes', { params }),
  get: (id: string) => api.get(`/scenes/${id}`),
  create: (data: any) => api.post('/scenes', data),
  update: (id: string, data: any) => api.patch(`/scenes/${id}`, data),
  delete: (id: string) => api.delete(`/scenes/${id}`),
};

// Quests API
export const questsApi = {
  list: (params?: { site_id?: string; quest_type?: string }) =>
    api.get('/quests', { params }),
  get: (id: string) => api.get(`/quests/${id}`),
  create: (data: any) => api.post('/quests', data),
  update: (id: string, data: any) => api.patch(`/quests/${id}`, data),
  delete: (id: string) => api.delete(`/quests/${id}`),
};

// Visitors API
export const visitorsApi = {
  list: (params?: { skip?: number; limit?: number }) =>
    api.get('/visitors', { params }),
  get: (id: string) => api.get(`/visitors/${id}`),
  getQuests: (id: string) => api.get(`/visitors/${id}/quests`),
};

// Chat API
export const chatApi = {
  send: (data: { npc_id: string; message: string; session_id?: string }) =>
    api.post('/chat', data),
  getGreeting: (data: { npc_id: string }) =>
    api.post('/chat/greeting', data),
};

// ============================================================
// Feedback API (P25a)
// ============================================================
export interface Feedback {
  id: string;
  trace_id: string;
  feedback_type: string;
  severity: string;
  status: string;
  assignee: string | null;
  group_name: string | null;
  sla_due_at: string | null;
  overdue_flag: boolean;
  user_comment: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeedbackStats {
  total: number;
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
  overdue_count: number;
  avg_time_to_resolve_hours: number | null;
}

export interface TriageRequest {
  assignee?: string;
  group_name?: string;
  sla_hours?: number;
}

export interface StatusUpdateRequest {
  status: string;
  resolution_note?: string;
}

// 使用代理路由（不直接调用 core-backend）
const adminApi = axios.create({
  baseURL: '/api/admin',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const feedbackApi = {
  list: (params?: {
    status?: string;
    severity?: string;
    overdue_only?: boolean;
    skip?: number;
    limit?: number;
  }) => adminApi.get<Feedback[]>('/feedback', { params }),
  
  get: (id: string) => adminApi.get<Feedback>(`/feedback/${id}`),
  
  stats: () => adminApi.get<FeedbackStats>('/feedback/stats'),
  
  triage: (id: string, data: TriageRequest) =>
    adminApi.post<Feedback>(`/feedback/${id}/triage`, data),
  
  updateStatus: (id: string, data: StatusUpdateRequest) =>
    adminApi.post<Feedback>(`/feedback/${id}/status`, data),
};

// ============================================================
// Evidence Gate Policy API (P25a)
// ============================================================
export interface PolicyVersion {
  version: string;
  created_at: string;
  operator: string;
  is_active: boolean;
}

export interface EvidenceGatePolicy {
  version: string;
  description: string;
  default_policy: Record<string, any>;
  site_policies: Record<string, any>;
  npc_policies: Record<string, any>;
  intent_overrides: Record<string, any>;
}

export const policyApi = {
  getActive: () => adminApi.get<EvidenceGatePolicy>('/policies/evidence-gate/active'),
  
  listVersions: () => adminApi.get<PolicyVersion[]>('/policies/evidence-gate/versions'),
  
  setActive: (policy: EvidenceGatePolicy) =>
    adminApi.post<{ version: string }>('/policies/evidence-gate', policy),
  
  rollback: (version: string) =>
    adminApi.post<{ version: string }>(`/policies/evidence-gate/rollback/${version}`),
};
