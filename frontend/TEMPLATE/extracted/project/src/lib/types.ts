export interface Cluster {
  id: string;
  name: string;
  keyword: string;
  description: string;
  color: string;
  paper_count: number;
  created_at: string;
}

export interface Paper {
  id: string;
  cluster_id: string;
  title: string;
  reference: string;
  abstract: string;
  is_representative: boolean;
  representation_score: number;
  published_at: string | null;
  is_weekly_pick: boolean;
  week_label: string;
  created_at: string;
  cluster?: Cluster;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}
