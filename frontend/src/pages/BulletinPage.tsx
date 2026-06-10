import { useState, useEffect, useMemo } from 'react';
import { AlertCircle, Newspaper, Clock, ChevronDown, ChevronUp, ExternalLink, Sparkles, Search, X } from 'lucide-react';
import { getBackendBaseUrl } from '../api/client';
import { getAuthHeaders } from '../lib/auth';
import { getImageForTopic } from '../lib/topicImages';
import type { Cluster, Digest, Paper } from '../lib/types';

interface BulletinGroup {
  cluster: Cluster;
  papers: Paper[];
  digest?: Digest | null;
}

interface PaperDetail extends Paper {
  doi?: string | null;
  source?: string | null;
  external_id?: string | null;
  authors?: string | null;
  venue?: string | null;
  primary_category?: string | null;
  citation_count?: number;
  has_pdf?: boolean;
}

interface CategoryOption {
  category: string;
  paper_count: number;
}

interface BulletinPreference {
  selection_type: 'clusters' | 'categories';
  cluster_ids: number[];
  categories: string[];
  notifications_enabled: boolean;
  notification_frequency: string;
  last_generated_at?: string | null;
}

interface UserBulletinResponse {
  configured: boolean;
  preference: BulletinPreference | null;
  bulletin: any[];
}

type SelectionType = 'clusters' | 'categories';

function normalizeBulletinGroups(data: any[]): BulletinGroup[] {
  return data.map((c: any) => {
    if (c.cluster && c.papers) {
      return {
        cluster: {
          id: String(c.cluster.id),
          name: c.cluster.name,
          keyword: c.cluster.keyword || c.cluster.name,
          paper_count: c.cluster.paper_count,
          color: c.cluster.color || '#10b981',
          description: c.cluster.description || '',
          created_at: c.cluster.created_at || new Date().toISOString(),
          metadata: c.cluster.metadata || {},
        },
        papers: (c.papers || []).map((a: any) => ({
          id: String(a.id),
          title: a.title,
          reference: a.reference || '',
          abstract: a.abstract || '',
          url: a.url || a.link || null,
          pdf_url: a.pdf_url || null,
          doi: a.doi || null,
          source: a.source || null,
          citation_count: a.citation_count || 0,
          has_pdf: Boolean(a.has_pdf ?? a.pdf_url),
          representation_score: a.representation_score || a.score || 0,
          cluster_id: String(c.cluster.id),
          published_at: a.published_at || a.publish_date || null,
          is_representative: Boolean(a.is_representative ?? true),
          is_weekly_pick: Boolean(a.is_weekly_pick ?? false),
          week_label: a.week_label || 'This Week',
          created_at: a.created_at || a.published_at || new Date().toISOString(),
        })),
        digest: c.digest || null,
      };
    }

    return {
      cluster: {
        id: String(c.cluster_id),
        name: c.cluster_name,
        keyword: c.cluster_name,
        paper_count: c.article_count,
        color: '#10b981',
        description: c.cluster_name || '',
        created_at: new Date().toISOString(),
      },
      papers: (c.articles || []).map((a: any) => ({
        id: String(a.id),
        title: a.title,
        reference: a.reference || '',
        abstract: a.abstract || '',
        url: a.url || a.link || null,
        pdf_url: a.pdf_url || null,
        representation_score: a.score || 0,
        cluster_id: String(c.cluster_id),
        published_at: a.publish_date || a.published_at || null,
        is_representative: true,
        is_weekly_pick: false,
        week_label: 'This Week',
        created_at: a.publish_date || a.published_at || new Date().toISOString(),
      })),
      digest: null,
    };
  });
}

export default function BulletinPage() {
  const [groups, setGroups] = useState<BulletinGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showWeekly, setShowWeekly] = useState(false);
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set());
  const [currentPageByCluster, setCurrentPageByCluster] = useState<Record<string, number>>({});
  const [selectedClusterIds, setSelectedClusterIds] = useState<Set<string>>(new Set());
  const [topicSearch, setTopicSearch] = useState('');

  const PAPERS_PER_PAGE = 10;
  const backendBaseUrl = getBackendBaseUrl();

  useEffect(() => {
    async function fetchData() {
      try {
        const response = await fetch(`${backendBaseUrl}/bulletin?limit=10&include_digests=true`);
        if (response.ok) {
          const data = await response.json();
          const groupsNormalized: BulletinGroup[] = data.map((c: any) => {
            if (c.cluster && c.papers) {
              return {
                cluster: {
                  id: String(c.cluster.id),
                  name: c.cluster.name,
                  keyword: c.cluster.keyword || c.cluster.name,
                  paper_count: c.cluster.paper_count,
                  color: c.cluster.color || '#10b981',
                  description: c.cluster.description || '',
                  created_at: c.cluster.created_at || new Date().toISOString(),
                  metadata: c.cluster.metadata || {},
                },
                papers: (c.papers || []).map((a: any) => ({
                  id: String(a.id),
                  title: a.title,
                  reference: a.reference || '',
                  abstract: a.abstract || '',
                  url: a.url || a.link || null,
                  pdf_url: a.pdf_url || null,
                  doi: a.doi || null,
                  source: a.source || null,
                  citation_count: a.citation_count || 0,
                  has_pdf: Boolean(a.has_pdf ?? a.pdf_url),
                  representation_score: a.representation_score || a.score || 0,
                  cluster_id: String(c.cluster.id),
                  published_at: a.published_at || a.publish_date || null,
                  is_representative: Boolean(a.is_representative ?? true),
                  is_weekly_pick: Boolean(a.is_weekly_pick ?? false),
                  week_label: a.week_label || 'This Week',
                  created_at: a.created_at || a.published_at || new Date().toISOString(),
                })),
                digest: c.digest || null,
              };
            }

            return {
              cluster: {
                id: String(c.cluster_id),
                name: c.cluster_name,
                keyword: c.cluster_name,
                paper_count: c.article_count,
                color: '#10b981',
                description: c.cluster_name || '',
                created_at: new Date().toISOString(),
              },
              papers: (c.articles || []).map((a: any) => ({
                id: String(a.id),
                title: a.title,
                reference: a.reference || '',
                abstract: a.abstract || '',
                url: a.url || a.link || null,
                pdf_url: a.pdf_url || null,
                representation_score: a.score || 0,
                cluster_id: String(c.cluster_id),
                published_at: a.publish_date || a.published_at || null,
                is_representative: true,
                is_weekly_pick: false,
                week_label: 'This Week',
                created_at: a.publish_date || a.published_at || new Date().toISOString(),
              })),
              digest: null,
            };
          });
          setGroups(groupsNormalized);
          setSelectedClusterIds(new Set(groupsNormalized.map((group) => group.cluster.id)));
          setError(null);
        } else {
          setError(`Backend returned HTTP ${response.status}`);
        }
      } catch (e) {
        console.error("Failed to fetch bulletin", e);
        setError("Backend is unavailable.");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const toggleCluster = (clusterId: string) => {
    setExpandedClusters((prev) => {
      const next = new Set(prev);
      if (next.has(clusterId)) {
        next.delete(clusterId);
      } else {
        next.add(clusterId);
        // Reset page to 1 when expanding
        setCurrentPageByCluster(p => ({ ...p, [clusterId]: 1 }));
      }
      return next;
    });
  };

  const topicOptions = useMemo(() => {
    const query = topicSearch.trim().toLowerCase();
    return groups.filter(({ cluster }) => {
      if (!query) {
        return true;
      }
      return `${cluster.name} ${cluster.keyword} ${cluster.description}`.toLowerCase().includes(query);
    });
  }, [groups, topicSearch]);

  const visibleGroups = useMemo(
    () => groups.filter(({ cluster }) => selectedClusterIds.has(cluster.id)),
    [groups, selectedClusterIds],
  );

  const toggleTopic = (clusterId: string) => {
    setSelectedClusterIds((prev) => {
      const next = new Set(prev);
      if (next.has(clusterId)) {
        next.delete(clusterId);
      } else {
        next.add(clusterId);
      }
      return next;
    });
  };

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-slate-50">
        <div className="flex items-center gap-3 text-slate-500">
          <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">Loading bulletin...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return <StateMessage title="Bulletin unavailable" body={error} />;
  }

  if (!groups.length) {
    return <StateMessage title="No clusters yet" body="Run ingestion, embeddings, and clustering to populate the bulletin." />;
  }

  const allPapers = visibleGroups.flatMap(g => g.papers);
  const weeklyPapers = [...allPapers]
    .sort((a, b) => (b.representation_score || 0) - (a.representation_score || 0))
    .slice(0, 6);
  const weeklyClusterIds = new Set(weeklyPapers.map((p) => p.cluster_id));

  return (
    <div className="h-screen overflow-y-auto bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4 sticky top-0 z-10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Newspaper size={20} className="text-emerald-500" />
            <div>
              <h1 className="text-lg font-semibold text-slate-800">Research Bulletin</h1>
              <p className="text-xs text-slate-500">Top representative papers by cluster</p>
            </div>
          </div>
          <button
            onClick={() => setShowWeekly(!showWeekly)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer ${
              showWeekly
                ? 'bg-emerald-500 text-white shadow-md shadow-emerald-500/20'
                : 'bg-white border border-slate-200 text-slate-700 hover:border-emerald-300 hover:text-emerald-600'
            }`}
          >
            <Clock size={14} />
            <span>Week's Best</span>
          </button>
        </div>
      </header>

      <div className="p-6">
        {/* Weekly Highlights Section */}
        {showWeekly && (
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-5">
              <Sparkles size={16} className="text-amber-500" />
              <h2 className="text-base font-semibold text-slate-800">This Week's Highlights</h2>
              <span className="px-2 py-0.5 bg-amber-50 text-amber-600 text-xs font-medium rounded-full">
                {weeklyPapers.length} papers
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {visibleGroups
                .filter((g) => weeklyClusterIds.has(g.cluster.id))
                .map(({ cluster, papers }) => {
                  const clusterWeekly = papers.slice(0, 2);
                  return (
                    <div
                      key={cluster.id}
                      className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:shadow-md transition-shadow duration-200"
                    >
                      <div className="relative h-28 overflow-hidden">
                        <img
                          src={getImageForTopic(cluster.keyword)}
                          alt={cluster.keyword}
                          className="w-full h-full object-cover"
                        />
                        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
                        <div className="absolute bottom-3 left-4 right-4">
                          <span
                            className="inline-block px-2 py-0.5 rounded text-[10px] font-semibold text-white uppercase tracking-wider"
                            style={{ background: cluster.color }}
                          >
                            {cluster.name}
                          </span>
                        </div>
                      </div>
                      <div className="p-4 space-y-3">
                        {clusterWeekly.map((paper) => (
                          <div key={paper.id} className="group">
                            <h4 className="text-sm font-semibold text-slate-800 group-hover:text-emerald-600 transition-colors line-clamp-2">
                              {paper.title}
                            </h4>
                            <p className="text-[10px] text-slate-400 mt-0.5 italic">{paper.reference}</p>
                            <p className="text-xs text-slate-600 mt-1.5 line-clamp-3 leading-relaxed">
                              {paper.abstract}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        )}

        <section className="mb-6 bg-white border border-slate-200 rounded-lg">
          <div className="flex flex-col gap-3 border-b border-slate-100 px-4 py-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-800">Topics</h2>
              <p className="text-xs text-slate-500">{selectedClusterIds.size} selected of {groups.length}</p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="relative">
                <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  value={topicSearch}
                  onChange={(event) => setTopicSearch(event.target.value)}
                  className="h-9 w-full rounded-md border border-slate-200 bg-white pl-8 pr-8 text-sm text-slate-700 outline-none transition-colors placeholder:text-slate-400 focus:border-emerald-400 sm:w-72"
                  placeholder="Search topics"
                />
                {topicSearch && (
                  <button
                    type="button"
                    onClick={() => setTopicSearch('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                    aria-label="Clear topic search"
                  >
                    <X size={13} />
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setSelectedClusterIds(new Set(groups.map((group) => group.cluster.id)))}
                  className="h-9 rounded-md border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 hover:border-emerald-300 hover:text-emerald-600"
                >
                  All
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedClusterIds(new Set())}
                  className="h-9 rounded-md border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 hover:border-rose-300 hover:text-rose-600"
                >
                  Clear
                </button>
              </div>
            </div>
          </div>
          <div className="max-h-52 overflow-y-auto p-3">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
              {topicOptions.map(({ cluster }) => {
                const checked = selectedClusterIds.has(cluster.id);
                return (
                  <label
                    key={cluster.id}
                    className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-md border px-3 py-2 transition-colors ${
                      checked
                        ? 'border-emerald-200 bg-emerald-50/70'
                        : 'border-slate-200 bg-white hover:border-slate-300'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleTopic(cluster.id)}
                      className="h-4 w-4 rounded border-slate-300 text-emerald-500 focus:ring-emerald-400"
                    />
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ background: cluster.color }}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-slate-800">{cluster.name}</span>
                      <span className="block text-xs text-slate-400">{cluster.paper_count} papers</span>
                    </span>
                  </label>
                );
              })}
            </div>
          </div>
        </section>

        {/* Cluster Groups */}
        <div className="space-y-3">
          {visibleGroups.length ? visibleGroups.map(({ cluster, papers, digest }) => {
            const isExpanded = expandedClusters.has(cluster.id);
            const currentPage = currentPageByCluster[cluster.id] || 1;
            const totalPages = Math.ceil(papers.length / PAPERS_PER_PAGE);
            
            // Slice papers for pagination
            const startIndex = (currentPage - 1) * PAPERS_PER_PAGE;
            const visiblePapers = isExpanded 
              ? papers.slice(startIndex, startIndex + PAPERS_PER_PAGE) 
              : papers.slice(0, 3);

            return (
              <div
                key={cluster.id}
                className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm"
              >
                {/* Cluster Header Accordion Trigger */}
                <button
                  onClick={() => toggleCluster(cluster.id)}
                  className="w-full flex items-center justify-between px-5 py-4 hover:bg-slate-50 transition-colors cursor-pointer border-b border-transparent hover:border-slate-100"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className="w-3 h-3 rounded-full shrink-0"
                      style={{ background: cluster.color }}
                    />
                    <h3 className="text-sm font-semibold text-slate-800 text-left">{cluster.name}</h3>
                    <span className="text-xs text-slate-400 font-medium">
                      ({papers.length} representative papers)
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className="text-xs font-semibold px-2 py-0.5 rounded-full"
                      style={{
                        background: `${cluster.color}15`,
                        color: cluster.color,
                      }}
                    >
                      {cluster.paper_count} total papers
                    </span>
                    {isExpanded ? (
                      <ChevronUp size={16} className="text-slate-400" />
                    ) : (
                      <ChevronDown size={16} className="text-slate-400" />
                    )}
                  </div>
                </button>

                {/* Papers Grid */}
                <div className={`px-5 pb-5 pt-3 bg-slate-50/30 ${isExpanded ? 'block' : 'block'}`}>
                  {digest?.summary && (
                    <div className="mb-4 rounded-lg border border-emerald-100 bg-emerald-50/60 p-3">
                      <p className="text-xs font-semibold text-emerald-700">Cluster digest</p>
                      <p className="mt-1 text-sm text-slate-700 leading-relaxed">{digest.summary}</p>
                      {digest.highlights?.length ? (
                        <ul className="mt-2 space-y-1 text-xs text-slate-600">
                          {digest.highlights.map((highlight) => (
                            <li key={highlight}>{highlight}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  )}
                  <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
                    {visiblePapers.length ? visiblePapers.map((paper) => (
                      <PaperCard key={paper.id} paper={paper} clusterColor={cluster.color} backendBaseUrl={backendBaseUrl} />
                    )) : (
                      <div className="col-span-full py-6 text-sm text-slate-500 text-center">No representative papers in this cluster.</div>
                    )}
                  </div>

                  {/* Pagination Controls inside accordion */}
                  {isExpanded && totalPages > 1 && (
                    <div className="flex justify-between items-center mt-4 pt-3 border-t border-slate-200/60 max-w-xl mx-auto">
                      <button
                        disabled={currentPage === 1}
                        onClick={(e) => {
                          e.stopPropagation();
                          setCurrentPageByCluster(prev => ({ ...prev, [cluster.id]: currentPage - 1 }));
                        }}
                        className="px-3 py-1 text-xs font-medium text-slate-600 bg-white border border-slate-200 rounded hover:bg-slate-50 hover:border-slate-300 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors shadow-sm"
                      >
                        Previous
                      </button>
                      <span className="text-xs text-slate-500 font-semibold">
                        Page {currentPage} of {totalPages}
                      </span>
                      <button
                        disabled={currentPage === totalPages}
                        onClick={(e) => {
                          e.stopPropagation();
                          setCurrentPageByCluster(prev => ({ ...prev, [cluster.id]: currentPage + 1 }));
                        }}
                        className="px-3 py-1 text-xs font-medium text-slate-600 bg-white border border-slate-200 rounded hover:bg-slate-50 hover:border-slate-300 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors shadow-sm"
                      >
                        Next
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          }) : (
            <div className="rounded-lg border border-slate-200 bg-white px-5 py-8 text-center text-sm text-slate-500">
              No topics selected.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StateMessage({ title, body }: { title: string; body: string }) {
  return (
    <div className="h-screen flex items-center justify-center bg-slate-50 p-6">
      <div className="max-w-md w-full bg-white border border-slate-200 rounded-xl p-6 text-center">
        <AlertCircle size={24} className="mx-auto text-amber-500" />
        <h1 className="mt-3 text-base font-semibold text-slate-800">{title}</h1>
        <p className="mt-1 text-sm text-slate-500">{body}</p>
      </div>
    </div>
  );
}

function PaperCard({
  paper,
  clusterColor,
  backendBaseUrl,
}: {
  paper: Paper;
  clusterColor: string;
  backendBaseUrl: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<PaperDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const openPaper = async () => {
    const nextExpanded = !expanded;
    setExpanded(nextExpanded);
    if (!nextExpanded || detail || detailLoading) {
      return;
    }

    setDetailLoading(true);
    setDetailError(null);
    try {
      const response = await fetch(`${backendBaseUrl}/bulletin/articles/${paper.id}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setDetail({
        ...paper,
        ...data,
        id: String(data.id),
        cluster_id: String(data.cluster_id ?? paper.cluster_id),
        published_at: data.published_at || paper.published_at,
        is_representative: paper.is_representative,
        representation_score: paper.representation_score,
        is_weekly_pick: paper.is_weekly_pick,
        week_label: paper.week_label,
        created_at: paper.created_at,
      });
    } catch (error) {
      console.error("Failed to fetch paper detail", error);
      setDetailError("Paper detail is unavailable.");
    } finally {
      setDetailLoading(false);
    }
  };

  const visiblePaper = detail || paper;
  const abstractText = visiblePaper.abstract || 'No abstract available.';
  const sourceUrl = visiblePaper.url || paper.url;
  const pdfUrl = visiblePaper.pdf_url || paper.pdf_url || null;

  return (
    <div
      className="group border border-slate-200/80 bg-white rounded-lg p-3.5 hover:border-slate-300 hover:shadow-md transition-all duration-200 cursor-pointer"
      onClick={openPaper}
    >
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold text-slate-800 group-hover:text-emerald-600 transition-colors line-clamp-2 leading-snug">
          {paper.title}
        </h4>
        {sourceUrl ? (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noreferrer"
            onClick={(event) => event.stopPropagation()}
            className="text-slate-300 hover:text-emerald-400 transition-colors"
          >
            <ExternalLink size={12} />
          </a>
        ) : (
          <ExternalLink size={12} className="text-slate-300 shrink-0 mt-0.5" />
        )}
      </div>
      <p className="text-[10px] text-slate-400 mt-1 italic">{paper.reference}</p>
      <div className="mt-2.5 flex items-center gap-2">
        <div className="flex-1 bg-slate-100 rounded-full h-1">
          <div
            className="h-1 rounded-full transition-all duration-500"
            style={{
              width: `${paper.representation_score * 100}%`,
              background: clusterColor,
              opacity: 0.7,
            }}
          />
        </div>
        <span className="text-[10px] text-slate-400 font-semibold">
          {Math.round(paper.representation_score * 100)}% Match
        </span>
      </div>
      <p className={`text-xs text-slate-600 mt-2.5 leading-relaxed ${expanded ? '' : 'line-clamp-3'}`}>
        {detailLoading ? 'Loading full abstract...' : abstractText}
      </p>
      {detailError && <p className="mt-2 text-xs text-rose-500">{detailError}</p>}
      {expanded && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {pdfUrl ? (
            <a
              href={pdfUrl}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => event.stopPropagation()}
              className="inline-flex h-8 items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2.5 text-xs font-semibold text-emerald-700 hover:border-emerald-300 hover:bg-emerald-100"
            >
              <ExternalLink size={12} />
              PDF
            </a>
          ) : null}
          {sourceUrl ? (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => event.stopPropagation()}
              className="inline-flex h-8 items-center gap-1 rounded-md border border-slate-200 bg-white px-2.5 text-xs font-semibold text-slate-600 hover:border-slate-300 hover:bg-slate-50"
            >
              <ExternalLink size={12} />
              Source
            </a>
          ) : null}
          {visiblePaper.doi ? (
            <span className="rounded-md bg-slate-100 px-2.5 py-1.5 text-xs font-medium text-slate-500">
              DOI: {visiblePaper.doi}
            </span>
          ) : null}
        </div>
      )}
      {paper.published_at && (
        <p className="text-[9px] font-medium text-slate-400 mt-2.5">
          Published: {new Date(paper.published_at).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
          })}
        </p>
      )}
    </div>
  );
}
