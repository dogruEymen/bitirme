import { useState, useEffect } from 'react';
import { Newspaper, Clock, ChevronDown, ChevronUp, ExternalLink, Sparkles } from 'lucide-react';
import { getImageForTopic } from '../lib/topicImages';
import type { Cluster, Paper } from '../lib/types';

interface BulletinGroup {
  cluster: Cluster;
  papers: Paper[];
}

export default function BulletinPage() {
  const [groups, setGroups] = useState<BulletinGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [showWeekly, setShowWeekly] = useState(false);
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set());
  const [currentPageByCluster, setCurrentPageByCluster] = useState<Record<string, number>>({});

  const PAPERS_PER_PAGE = 10;
  const backendHost = window.location.hostname;
  const backendBaseUrl = `http://${backendHost}:8000`;

  useEffect(() => {
    async function fetchData() {
      try {
        const response = await fetch(`${backendBaseUrl}/bulletin?limit=50`);
        if (response.ok) {
          const data = await response.json();
          // Normalize backend response into BulletinGroup[]
          const groupsNormalized: BulletinGroup[] = data.map((c: any) => {
            // Support two response shapes:
            // Legacy: { cluster_id, cluster_name, article_count, articles: [...] }
            // New: { cluster: { id, name, ... }, papers: [...] }
            if (c.cluster && c.papers) {
              return {
                cluster: {
                  id: String(c.cluster.id),
                  name: c.cluster.name,
                  keyword: c.cluster.keyword || c.cluster.name,
                  paper_count: c.cluster.paper_count,
                  color: c.cluster.color || '#10b981',
                },
                papers: (c.papers || []).map((a: any) => ({
                  id: a.id,
                  title: a.title,
                  reference: a.reference || '',
                  abstract: a.abstract || '',
                  representation_score: a.representation_score || a.score || 0,
                  cluster_id: c.cluster.id,
                  published_at: a.published_at || a.publish_date || null,
                })),
              };
            }

            // Fallback to legacy
            return {
              cluster: {
                id: String(c.cluster_id),
                name: c.cluster_name,
                keyword: c.cluster_name,
                paper_count: c.article_count,
                color: '#10b981',
              },
              papers: (c.articles || []).map((a: any) => ({
                id: a.id,
                title: a.title,
                reference: a.reference || '',
                abstract: a.abstract || '',
                representation_score: a.score || 0,
                cluster_id: c.cluster_id,
                published_at: a.publish_date || a.published_at || null,
              })),
            };
          });
          setGroups(groupsNormalized);
        }
      } catch (e) {
        console.error("Failed to fetch bulletin", e);
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

  // Generate weekly picks (say, papers with highest representation score or marked picks)
  const allPapers = groups.flatMap(g => g.papers);
  const weeklyPapers = allPapers.slice(0, 6); // Just get the top 6 papers as weekly picks dynamically
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
              {groups
                .filter((g) => weeklyClusterIds.has(g.cluster.id))
                .map(({ cluster, papers }) => {
                  const clusterWeekly = papers.slice(0, 2); // Show top 2 of weekly picks for this cluster
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

        {/* Cluster Groups */}
        <div className="space-y-3">
          {groups.map(({ cluster, papers }) => {
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
                  <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
                    {visiblePapers.map((paper) => (
                      <PaperCard key={paper.id} paper={paper} clusterColor={cluster.color} />
                    ))}
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
          })}
        </div>
      </div>
    </div>
  );
}

function PaperCard({ paper, clusterColor }: { paper: Paper; clusterColor: string }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="group border border-slate-200/80 bg-white rounded-lg p-3.5 hover:border-slate-300 hover:shadow-md transition-all duration-200 cursor-pointer"
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold text-slate-800 group-hover:text-emerald-600 transition-colors line-clamp-2 leading-snug">
          {paper.title}
        </h4>
        <ExternalLink size={12} className="text-slate-300 shrink-0 mt-0.5 group-hover:text-emerald-400 transition-colors" />
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
        {paper.abstract}
      </p>
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
