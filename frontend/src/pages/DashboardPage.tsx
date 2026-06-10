import { useEffect, useState } from 'react';
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, ScatterChart, Scatter, ZAxis,
  AreaChart, Area, LineChart, Line, Legend,
} from 'recharts';
import { AlertCircle, Database, Filter, FileText, Layers, TrendingUp, type LucideIcon } from 'lucide-react';
import { getBackendBaseUrl } from '../api/client';

interface BarDatum {
  name: string;
  fullName?: string;
  count?: number;
  papers: number;
  color: string;
}

interface PieDatum {
  name: string;
  value: number;
  color: string;
}

interface ScatterDatum {
  cluster: string;
  fullName?: string;
  x: number;
  y: number;
  z: number;
  color: string;
}

interface ClusterRow {
  id: string | number;
  name: string;
  keyword: string;
  paper_count: number;
  color: string;
  metadata: Record<string, unknown>;
}

interface ClusterPayload extends ClusterRow {
  representation_score?: number;
}

interface DistributionItem {
  source?: string;
  category?: string;
  count: number;
}

interface RisingTopic {
  cluster_id: string;
  name: string;
  paper_count: number;
  last_30d: number;
  acceleration_30d: number;
  score: number;
  color?: string;
}

interface TrendSeriesItem {
  cluster_id: string;
  cluster_name: string;
  month: string;
  monthKey: string;
  count: number;
}

interface AnalyticsMetrics {
  totalPapers?: number;
  activeClusters?: number;
  avgPapersPerCluster?: number;
  weeklyPicks?: number;
  clusteredPapers?: number;
  pdfAvailable?: number;
}

interface ClusterQuality {
  outlierCount?: number;
  outlierRatio?: number;
  largestClusterId?: string | null;
  largestClusterName?: string | null;
  largestClusterCount?: number;
  largestClusterRatio?: number;
  avgRepresentationScore?: number;
  clusteredPapers?: number;
  totalPapersWithEmbedding?: number;
}

interface AnalyticsPayload {
  schemaVersion?: string;
  metrics?: AnalyticsMetrics;
  barData?: Array<Partial<BarDatum> & { name: string }>;
  pieData?: PieDatum[];
  scatterData?: ScatterDatum[];
  monthlyData?: Array<{ month: string; publications?: number; count?: number }>;
  clusters?: ClusterPayload[];
  sourceDistribution?: DistributionItem[];
  categoryDistribution?: DistributionItem[];
  clusterTrendSeries?: TrendSeriesItem[];
  risingTopics?: RisingTopic[];
  clusterQuality?: ClusterQuality;
}

type PeriodValue = '3m' | '6m' | '12m' | 'all';

export default function DashboardPage() {
  const [data, setData] = useState<AnalyticsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [period, setPeriod] = useState<PeriodValue>('12m');

  const backendBaseUrl = getBackendBaseUrl();

  useEffect(() => {
    const controller = new AbortController();

    async function fetchData() {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (sourceFilter !== 'all') params.set('source', sourceFilter);
        if (categoryFilter !== 'all') params.set('category', categoryFilter);
        params.set('period', period);

        const response = await fetch(`${backendBaseUrl}/analytics?${params.toString()}`, {
          signal: controller.signal,
        });
        if (response.ok) {
          const json = await response.json() as AnalyticsPayload;
          setData(json);
          setError(null);
        } else {
          setError(`Backend returned HTTP ${response.status}`);
        }
      } catch (e) {
        if ((e as Error).name !== 'AbortError') {
          console.error('Failed to fetch analytics data', e);
          setError('Backend is unavailable.');
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    fetchData();
    return () => controller.abort();
  }, [backendBaseUrl, categoryFilter, period, sourceFilter]);

  if (loading && !data) {
    return (
      <div className="h-screen flex items-center justify-center bg-slate-50">
        <div className="flex items-center gap-3 text-slate-500">
          <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">Loading analytics...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return <StateMessage title="Analytics unavailable" body={error || 'No analytics response was returned.'} />;
  }

  const metrics = data.metrics || {};
  const barData: BarDatum[] = (data.barData || []).map((item) => ({
    ...item,
    papers: item.papers ?? item.count ?? 0,
    fullName: item.fullName || item.name,
    color: item.color || '#10b981',
  }));
  const pieData: PieDatum[] = data.pieData || [];
  const scatterData: ScatterDatum[] = data.scatterData || [];
  const monthlyData = (data.monthlyData || []).map((m) => ({
    month: m.month,
    publications: m.publications ?? m.count ?? 0,
  }));

  const totalPapers = metrics.totalPapers || 0;
  const avgPerCluster = Math.round(metrics.avgPapersPerCluster || 0);
  const activeClustersCount = metrics.activeClusters || 0;
  const weeklyPicks = metrics.weeklyPicks || 0;
  const clusterQuality = data.clusterQuality || {};
  const risingTopics: RisingTopic[] = data.risingTopics || [];
  const sourceOptions = (data.sourceDistribution || []) as DistributionItem[];
  const categoryOptions = (data.categoryDistribution || []) as DistributionItem[];
  const trendSeries = (data.clusterTrendSeries || []) as TrendSeriesItem[];
  const topClusterPaperCount = barData[0]?.papers || 0;
  const clusters: ClusterRow[] = data.clusters?.length
    ? data.clusters.map((c) => ({
      id: c.id,
      name: c.name,
      keyword: c.keyword || c.name,
      paper_count: c.paper_count || 0,
      color: c.color || '#10b981',
      metadata: c.metadata || {},
    }))
    : barData.map((c, idx) => ({
      id: idx,
      name: c.name,
      keyword: c.name,
      paper_count: c.count ?? c.papers ?? 0,
      color: c.color,
      metadata: {},
    }));

  const trendChart = buildTrendChartRows(trendSeries);
  const trendClusterMap = buildTrendClusterMap(trendSeries, clusters);
  const trendClusterIds = Object.keys(trendClusterMap).slice(0, 8);

  return (
    <div className="h-screen overflow-y-auto bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-800">Analytics Dashboard</h1>
            <p className="text-xs text-slate-500 mt-0.5">Academic paper cluster trends, quality, and distribution</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <FilterSelect
              label="Source"
              value={sourceFilter}
              onChange={setSourceFilter}
              options={sourceOptions.map((item) => ({
                value: item.source || 'unknown',
                label: `${item.source || 'unknown'} (${item.count})`,
              }))}
            />
            <FilterSelect
              label="Category"
              value={categoryFilter}
              onChange={setCategoryFilter}
              options={categoryOptions.map((item) => ({
                value: item.category || 'unknown',
                label: `${item.category || 'unknown'} (${item.count})`,
              }))}
            />
            <PeriodControl value={period} onChange={setPeriod} />
            <span className="inline-flex h-9 items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-3 text-xs font-medium text-slate-600">
              <Filter size={14} />
              {data.schemaVersion || 'analytics:v1'}
            </span>
          </div>
        </div>
      </header>

      <div className="p-6 space-y-6">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard icon={FileText} label="Total Papers" value={totalPapers.toLocaleString()} trend={period.toUpperCase()} color="emerald" />
          <MetricCard icon={Layers} label="Active Clusters" value={String(activeClustersCount)} trend={`${metrics.clusteredPapers || 0} clustered`} color="blue" />
          <MetricCard icon={TrendingUp} label="Avg Papers/Cluster" value={avgPerCluster.toString()} trend="Mean" color="amber" />
          <MetricCard icon={Database} label="Weekly Picks" value={weeklyPicks.toString()} trend="Last 7d" color="rose" />
        </div>

        {totalPapers === 0 && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            No articles match the selected filters. Adjust source, category, or period to widen the analytics window.
          </div>
        )}

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <div className="xl:col-span-2 bg-white rounded-lg border border-slate-200 p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-semibold text-slate-800">Rising Topics</h3>
                <p className="text-xs text-slate-500 mt-0.5">Clusters ranked by 7/30/90 day acceleration</p>
              </div>
            </div>
            {risingTopics.length ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {risingTopics.slice(0, 6).map((topic, index) => (
                  <div key={topic.cluster_id} className="rounded-md border border-slate-200 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ background: topic.color || '#10b981' }} />
                          <h4 className="truncate text-sm font-semibold text-slate-800">{topic.name}</h4>
                        </div>
                        <p className="mt-1 text-xs text-slate-500">{topic.last_30d} papers in last 30 days</p>
                      </div>
                      <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">#{index + 1}</span>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                      <MiniStat label="Accel 30d" value={`${formatSigned(topic.acceleration_30d)}x`} />
                      <MiniStat label="Score" value={topic.score.toFixed(2)} />
                      <MiniStat label="Total" value={String(topic.paper_count)} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <SmallEmptyState text="No rising topics for selected filters." />
            )}
          </div>

          <div className="bg-white rounded-lg border border-slate-200 p-5">
            <h3 className="text-sm font-semibold text-slate-800 mb-1">Cluster Quality</h3>
            <p className="text-xs text-slate-500 mb-4">Signals from the latest clustering run</p>
            <div className="grid grid-cols-2 gap-3">
              <QualityStat label="Outlier Ratio" value={formatPercent(clusterQuality.outlierRatio)} warn={(clusterQuality.outlierRatio || 0) > 0.35} />
              <QualityStat label="Largest Ratio" value={formatPercent(clusterQuality.largestClusterRatio)} warn={(clusterQuality.largestClusterRatio || 0) > 0.45} />
              <QualityStat label="Avg Rep Score" value={formatPercent(clusterQuality.avgRepresentationScore)} warn={(clusterQuality.avgRepresentationScore || 0) < 0.4} />
              <QualityStat label="Embedded Papers" value={String(clusterQuality.totalPapersWithEmbedding || 0)} />
            </div>
            {clusterQuality.largestClusterName && (
              <p className="mt-4 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
                Largest cluster: <span className="font-semibold text-slate-800">{clusterQuality.largestClusterName}</span>
              </p>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 bg-white rounded-lg border border-slate-200 p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-semibold text-slate-800">Cluster Trend</h3>
                <p className="text-xs text-slate-500 mt-0.5">Monthly growth for top clusters</p>
              </div>
            </div>
            {trendChart.length && trendClusterIds.length ? (
              <div className="w-full h-[320px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendChart} margin={{ top: 5, right: 16, left: -10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#64748b' }} />
                    <YAxis tick={{ fontSize: 11, fill: '#64748b' }} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    {trendClusterIds.map((clusterId) => (
                      <Line
                        key={clusterId}
                        type="monotone"
                        dataKey={`cluster_${clusterId}`}
                        name={trendClusterMap[clusterId].name}
                        stroke={trendClusterMap[clusterId].color}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4 }}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <SmallEmptyState text="No cluster trend data for selected filters." />
            )}
          </div>

          <div className="bg-white rounded-lg border border-slate-200 p-5">
            <h3 className="text-sm font-semibold text-slate-800 mb-1">Cluster Proportions</h3>
            <p className="text-xs text-slate-500 mb-4">Relative size of top 8 clusters</p>
            {pieData.length ? (
              <div className="w-full h-[220px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={80} paddingAngle={3} dataKey="value">
                      {pieData.map((entry, index) => (
                        <Cell key={index} fill={entry.color} fillOpacity={0.85} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={tooltipStyle} formatter={(value) => [`${value ?? 0} papers`]} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <SmallEmptyState text="No clusters yet." />
            )}
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 mt-2">
              {pieData.slice(0, 8).map((d) => (
                <div key={d.name} className="flex items-center gap-1.5 text-[10px]">
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ background: d.color }} />
                  <span className="text-slate-600 truncate">{d.name.length > 16 ? d.name.slice(0, 16) + '...' : d.name}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-white rounded-lg border border-slate-200 p-5">
            <h3 className="text-sm font-semibold text-slate-800 mb-1">Cluster Size vs. Representation Quality</h3>
            <p className="text-xs text-slate-500 mb-4">Papers count vs average representation score</p>
            <div className="w-full h-[280px]">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="x" name="Papers" tick={{ fontSize: 11, fill: '#64748b' }} />
                  <YAxis dataKey="y" name="Score" tick={{ fontSize: 11, fill: '#64748b' }} domain={[0, 100]} />
                  <ZAxis dataKey="z" range={[60, 300]} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(value, name) => [name === 'Papers' ? value : `${value}%`, name]} />
                  <Scatter data={scatterData} fillOpacity={0.7}>
                    {scatterData.map((entry, index) => (
                      <Cell key={index} fill={entry.color} />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 p-5">
            <h3 className="text-sm font-semibold text-slate-800 mb-1">Publication Trend</h3>
            <p className="text-xs text-slate-500 mb-4">Monthly publication volume from selected filters</p>
            <div className="w-full h-[280px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={monthlyData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#64748b' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#64748b' }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <defs>
                    <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <Area type="monotone" dataKey="publications" stroke="#10b981" strokeWidth={2} fill="url(#areaGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg border border-slate-200 p-5">
          <h3 className="text-sm font-semibold text-slate-800 mb-4">All Clusters Overview</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="text-left py-2 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Cluster</th>
                  <th className="text-left py-2 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Keyword</th>
                  <th className="text-right py-2 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Papers</th>
                  <th className="text-right py-2 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Share</th>
                  <th className="text-left py-2 px-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Distribution</th>
                </tr>
              </thead>
              <tbody>
                {clusters.length ? clusters.map((c) => (
                  <tr key={c.id} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: c.color }} />
                        <span className="font-medium text-slate-700">{c.name}</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-slate-500">{c.keyword}</td>
                    <td className="py-2.5 px-3 text-right font-medium text-slate-700">{c.paper_count}</td>
                    <td className="py-2.5 px-3 text-right text-slate-500">
                      {totalPapers ? ((c.paper_count / totalPapers) * 100).toFixed(1) : 0}%
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="w-full bg-slate-100 rounded-full h-1.5">
                        <div
                          className="h-1.5 rounded-full transition-all duration-500"
                          style={{
                            width: `${topClusterPaperCount ? (c.paper_count / topClusterPaperCount) * 100 : 0}%`,
                            background: c.color,
                            opacity: 0.8,
                          }}
                        />
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-sm text-slate-500">No clusters yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

const tooltipStyle = {
  background: '#fff',
  border: '1px solid #e2e8f0',
  borderRadius: '8px',
  fontSize: '12px',
};

function buildTrendChartRows(series: TrendSeriesItem[]) {
  const byMonth: Record<string, Record<string, string | number>> = {};
  for (const item of series) {
    const row = byMonth[item.monthKey] || { month: item.month, monthKey: item.monthKey };
    row[`cluster_${item.cluster_id}`] = item.count;
    byMonth[item.monthKey] = row;
  }
  return Object.values(byMonth).sort((a, b) => String(a.monthKey).localeCompare(String(b.monthKey)));
}

function buildTrendClusterMap(series: TrendSeriesItem[], clusters: ClusterRow[]) {
  const clusterColors = new Map(clusters.map((cluster) => [String(cluster.id), cluster.color]));
  const result: Record<string, { name: string; color: string }> = {};
  for (const item of series) {
    if (!result[item.cluster_id]) {
      result[item.cluster_id] = {
        name: item.cluster_name,
        color: clusterColors.get(item.cluster_id) || '#10b981',
      };
    }
  }
  return result;
}

function formatPercent(value: number | undefined) {
  return `${Math.round((value || 0) * 100)}%`;
}

function formatSigned(value: number) {
  return value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2);
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-500">
      <span className="font-medium">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-7 min-w-28 bg-transparent text-xs font-semibold text-slate-700 outline-none"
      >
        <option value="all">All</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  );
}

function PeriodControl({ value, onChange }: { value: PeriodValue; onChange: (value: PeriodValue) => void }) {
  const options: { value: PeriodValue; label: string }[] = [
    { value: '3m', label: '3M' },
    { value: '6m', label: '6M' },
    { value: '12m', label: '12M' },
    { value: 'all', label: 'All' },
  ];

  return (
    <div className="inline-flex h-9 rounded-md border border-slate-200 bg-white p-1">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={`min-w-10 rounded px-2 text-xs font-semibold transition ${
            value === option.value ? 'bg-slate-800 text-white' : 'text-slate-500 hover:bg-slate-100'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function StateMessage({ title, body }: { title: string; body: string }) {
  return (
    <div className="h-screen flex items-center justify-center bg-slate-50 p-6">
      <div className="max-w-md w-full bg-white border border-slate-200 rounded-lg p-6 text-center">
        <AlertCircle size={24} className="mx-auto text-amber-500" />
        <h1 className="mt-3 text-base font-semibold text-slate-800">{title}</h1>
        <p className="mt-1 text-sm text-slate-500">{body}</p>
      </div>
    </div>
  );
}

function SmallEmptyState({ text }: { text: string }) {
  return <div className="h-[220px] flex items-center justify-center text-sm text-slate-500">{text}</div>;
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded bg-slate-50 px-2 py-1.5">
      <p className="text-[10px] font-medium uppercase text-slate-400">{label}</p>
      <p className="mt-0.5 text-sm font-semibold text-slate-800">{value}</p>
    </div>
  );
}

function QualityStat({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className={`rounded-md border px-3 py-2 ${warn ? 'border-amber-200 bg-amber-50' : 'border-slate-200 bg-slate-50'}`}>
      <p className={`text-[10px] font-medium uppercase ${warn ? 'text-amber-600' : 'text-slate-400'}`}>{label}</p>
      <p className={`mt-1 text-lg font-bold ${warn ? 'text-amber-800' : 'text-slate-800'}`}>{value}</p>
    </div>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  trend,
  color,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  trend: string;
  color: string;
}) {
  const colorMap: Record<string, { bg: string; icon: string; text: string }> = {
    emerald: { bg: 'bg-emerald-50', icon: 'text-emerald-600', text: 'text-emerald-600' },
    blue: { bg: 'bg-blue-50', icon: 'text-blue-600', text: 'text-blue-600' },
    amber: { bg: 'bg-amber-50', icon: 'text-amber-600', text: 'text-amber-600' },
    rose: { bg: 'bg-rose-50', icon: 'text-rose-600', text: 'text-rose-600' },
  };
  const c = colorMap[color] || colorMap.emerald;

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <div className="flex items-center justify-between">
        <div className={`w-9 h-9 rounded-lg ${c.bg} flex items-center justify-center`}>
          <Icon size={16} className={c.icon} />
        </div>
        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-50 border border-slate-100 text-slate-500">{trend}</span>
      </div>
      <p className="mt-3 text-2xl font-bold text-slate-800">{value}</p>
      <p className="text-xs text-slate-500 mt-0.5">{label}</p>
    </div>
  );
}
