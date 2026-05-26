import { useState, useEffect } from 'react';
import { Newspaper, Clock, ChevronDown, ChevronUp, ExternalLink, Sparkles } from 'lucide-react';
import { supabase } from '../lib/supabase';
import { getImageForTopic } from '../lib/topicImages';
import type { Cluster, Paper } from '../lib/types';

export default function BulletinPage() {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);
  const [showWeekly, setShowWeekly] = useState(false);
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set());

  useEffect(() => {
    async function fetchData() {
      const [clusterRes, paperRes] = await Promise.all([
        supabase.from('clusters').select('*').order('paper_count', { ascending: false }),
        supabase.from('papers').select('*').order('representation_score', { ascending: false }),
      ]);
      if (clusterRes.data) setClusters(clusterRes.data);
      if (paperRes.data) setPapers(paperRes.data);
      setLoading(false);
    }
    fetchData();
  }, []);

  const toggleCluster = (clusterId: string) => {
    setExpandedClusters((prev) => {
      const next = new Set(prev);
      if (next.has(clusterId)) next.delete(clusterId);
      else next.add(clusterId);
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

  const weeklyPapers = papers.filter((p) => p.is_weekly_pick);
  const weeklyClusterIds = new Set(weeklyPapers.map((p) => p.cluster_id));

  const representativeByCluster = clusters.map((cluster) => {
    const clusterPapers = papers
      .filter((p) => p.cluster_id === cluster.id && p.is_representative)
      .sort((a, b) => b.representation_score - a.representation_score)
      .slice(0, 5);
    return { cluster, papers: clusterPapers };
  }).filter((group) => group.papers.length > 0);

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
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
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
              {clusters
                .filter((c) => weeklyClusterIds.has(c.id))
                .map((cluster) => {
                  const clusterWeekly = weeklyPapers.filter((p) => p.cluster_id === cluster.id);
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
                            className="inline-block px-2 py-0.5 rounded text-xs font-medium text-white"
                            style={{ background: cluster.color }}
                          >
                            {cluster.name}
                          </span>
                        </div>
                      </div>
                      <div className="p-4 space-y-3">
                        {clusterWeekly.slice(0, 2).map((paper) => (
                          <div key={paper.id} className="group cursor-pointer">
                            <h4 className="text-sm font-semibold text-slate-800 group-hover:text-emerald-600 transition-colors line-clamp-2">
                              {paper.title}
                            </h4>
                            <p className="text-xs text-slate-500 mt-1">{paper.reference}</p>
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
          {representativeByCluster.map(({ cluster, papers: clusterPapers }) => {
            const isExpanded = expandedClusters.has(cluster.id);
            const displayPapers = isExpanded ? clusterPapers : clusterPapers.slice(0, 3);

            return (
              <div
                key={cluster.id}
                className="bg-white rounded-xl border border-slate-200 overflow-hidden"
              >
                {/* Cluster Header */}
                <button
                  onClick={() => toggleCluster(cluster.id)}
                  className="w-full flex items-center justify-between px-5 py-3.5 hover:bg-slate-25 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className="w-3 h-3 rounded-full shrink-0"
                      style={{ background: cluster.color }}
                    />
                    <h3 className="text-sm font-semibold text-slate-800">{cluster.name}</h3>
                    <span className="text-xs text-slate-400">
                      {clusterPapers.length > 0 ? `${clusterPapers.length} top papers` : ''}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className="text-xs font-medium px-2 py-0.5 rounded-full"
                      style={{
                        background: `${cluster.color}15`,
                        color: cluster.color,
                      }}
                    >
                      {cluster.paper_count} papers
                    </span>
                    {isExpanded ? (
                      <ChevronUp size={16} className="text-slate-400" />
                    ) : (
                      <ChevronDown size={16} className="text-slate-400" />
                    )}
                  </div>
                </button>

                {/* Papers Grid */}
                <div className="px-5 pb-4">
                  <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
                    {displayPapers.map((paper) => (
                      <PaperCard key={paper.id} paper={paper} clusterColor={cluster.color} />
                    ))}
                  </div>
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
      className="group border border-slate-100 rounded-lg p-3.5 hover:border-slate-200 hover:shadow-sm transition-all duration-200 cursor-pointer"
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold text-slate-800 group-hover:text-emerald-600 transition-colors line-clamp-2 leading-snug">
          {paper.title}
        </h4>
        <ExternalLink size={12} className="text-slate-300 shrink-0 mt-0.5 group-hover:text-emerald-400 transition-colors" />
      </div>
      <p className="text-xs text-slate-500 mt-1.5 italic">{paper.reference}</p>
      <div className="mt-2 flex items-center gap-2">
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
        <span className="text-[10px] text-slate-400 font-medium">
          {Math.round(paper.representation_score * 100)}%
        </span>
      </div>
      <p className={`text-xs text-slate-600 mt-2 leading-relaxed ${expanded ? '' : 'line-clamp-3'}`}>
        {paper.abstract}
      </p>
      {paper.published_at && (
        <p className="text-[10px] text-slate-400 mt-2">
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
