export interface Cluster {
  id: string;
  name: string;
  keyword: string;
  description: string;
  color: string;
  paper_count: number;
  created_at: string;
  metadata?: Record<string, unknown>;
}

export interface Paper {
  id: string;
  cluster_id: string;
  title: string;
  reference: string;
  abstract: string;
  url?: string;
  pdf_url?: string | null;
  doi?: string | null;
  source?: string | null;
  venue?: string | null;
  authors?: string | null;
  citation_count?: number;
  has_pdf?: boolean;
  is_representative: boolean;
  representation_score: number;
  published_at: string | null;
  is_weekly_pick: boolean;
  week_label: string;
  created_at: string;
  cluster?: Cluster;
}

export interface Digest {
  cluster_id: number;
  summary: string;
  highlights: string[];
  representative_sources: Array<{
    source_id: string;
    article_id: number;
    title: string;
    doi?: string | null;
    url?: string | null;
    venue?: string | null;
    publish_date?: string | null;
  }>;
  article_ids: number[];
  created_at?: string | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export type ClusterOption = Cluster;

export interface CategoryOption {
  category: string;
  paper_count: number;
}

export interface BulletinPreferenceViewModel {
  selection_type: 'clusters' | 'categories';
  cluster_ids: number[];
  categories: string[];
  notifications_enabled: boolean;
  notification_frequency: string;
  last_generated_at?: string | null;
}
