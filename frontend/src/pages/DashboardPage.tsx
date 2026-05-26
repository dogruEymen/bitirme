import { useState, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, ScatterChart, Scatter, ZAxis,
  AreaChart, Area,
} from 'recharts';
import { Database, TrendingUp, FileText, Layers } from 'lucide-react';
import type { Cluster, Paper } from '../lib/types';

export default function DashboardPage() {
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);

  const backendHost = window.location.hostname;
  const backendBaseUrl = `http://${backendHost}:8000`;

  useEffect(() => {
    async function fetchData() {
      try {
        const response = await fetch(`${backendBaseUrl}/analytics`);
        if (response.ok) {
          const json = await response.json();
          setData(json);
        }
      } catch (e) {
        console.error("Failed to fetch analytics data", e);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  if (loading || !data) {
    return (
      <div className="h-screen flex items-center justify-center bg-slate-50">
        <div className="flex items-center gap-3 text-slate-500">
          <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">Loading analytics...</span>
        </div>
      </div>
    );
  }
  // Our backend returns: metrics, barData, pieData, scatterData, monthlyData
  const metrics = data.metrics || {};
  const barData = data.barData || [];
  const pieData = data.pieData || [];
  const scatterData = data.scatterData || [];
  const monthlyData = (data.monthlyData || []).map((m: any) => ({ month: m.month, publications: m.count }));

  const totalPapers = metrics.totalPapers || 0;
  const avgPerCluster = Math.round(metrics.avgPapersPerCluster || 0);
  const activeClustersCount = metrics.activeClusters || 0;
  const weeklyPicks = metrics.weeklyPicks || 0;

  const topCluster = barData[0] || null;
  const clusters = barData.map((c: any, idx: number) => ({
    id: idx,
    name: c.name,
    keyword: c.name,
    paper_count: c.count || c.papers || 0,
    color: c.color || '#10b981',
  }));

  return (
    <div className="h-screen overflow-y-auto bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-800">Analytics Dashboard</h1>
            <p className="text-xs text-slate-500 mt-0.5">Academic paper cluster analysis and distribution</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="px-3 py-1.5 bg-slate-100 text-slate-600 text-xs font-medium rounded-lg">
              Live DB Data
            </span>
          </div>
        </div>
      </header>

      <div className="p-6 space-y-6">
        {/* Metric Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            icon={FileText}
            label="Total Papers"
            value={totalPapers.toLocaleString()}
            trend="Live"
            color="emerald"
          />
          <MetricCard
            icon={Layers}
            label="Active Clusters"
            value={String(activeClustersCount)}
            trend={`+${activeClustersCount}`}
            color="blue"
          />
          <MetricCard
            icon={TrendingUp}
            label="Avg Papers/Cluster"
            value={avgPerCluster.toString()}
            trend="Optimal"
            color="amber"
          />
          <MetricCard
            icon={Database}
            label="Weekly Picks"
            value={weeklyPicks.toString()}
            trend="Highlight"
            color="rose"
          />
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Bar Chart - Paper Distribution */}
          <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-semibold text-slate-800">Paper Distribution by Cluster</h3>
                <p className="text-xs text-slate-500 mt-0.5">Number of papers per research cluster</p>
              </div>
            </div>
            <div className="w-full h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={barData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#64748b' }} angle={-30} textAnchor="end" height={60} />
                  <YAxis tick={{ fontSize: 11, fill: '#64748b' }} />
                  <Tooltip
                    contentStyle={{
                      background: '#fff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                    formatter={(value: number, _name: string, props: any) => [value, props.payload.fullName]}
                  />
                  <Bar dataKey="papers" radius={[4, 4, 0, 0]}>
                    {barData.map((entry, index) => (
                      <Cell key={index} fill={entry.color} fillOpacity={0.85} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Pie Chart - Cluster Proportions */}
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <h3 className="text-sm font-semibold text-slate-800 mb-1">Cluster Proportions</h3>
            <p className="text-xs text-slate-500 mb-4">Relative size of top 8 clusters</p>
            <div className="w-full h-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={80}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={index} fill={entry.color} fillOpacity={0.85} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: '#fff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                    formatter={(value: number) => [`${value} papers`]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
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

        {/* Second Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Scatter - Size vs Representation Score */}
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <h3 className="text-sm font-semibold text-slate-800 mb-1">Cluster Size vs. Representation Quality</h3>
            <p className="text-xs text-slate-500 mb-4">Papers count vs average representation score</p>
            <div className="w-full h-[280px]">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="x" name="Papers" tick={{ fontSize: 11, fill: '#64748b' }} />
                  <YAxis dataKey="y" name="Score" tick={{ fontSize: 11, fill: '#64748b' }} domain={[50, 100]} />
                  <ZAxis dataKey="z" range={[60, 300]} />
                  <Tooltip
                    contentStyle={{
                      background: '#fff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                    formatter={(value: number, name: string) => [
                      name === 'Papers' ? value : `${value}%`,
                      name,
                    ]}
                    labelFormatter={(_, payload) => {
                      if (payload?.[0]?.payload?.fullName) return payload[0].payload.fullName;
                      return '';
                    }}
                  />
                  <Scatter data={scatterData} fillOpacity={0.7}>
                    {scatterData.map((entry, index) => (
                      <Cell key={index} fill={entry.color} />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Area Chart - Publication Trend */}
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <h3 className="text-sm font-semibold text-slate-800 mb-1">Publication Trend</h3>
            <p className="text-xs text-slate-500 mb-4">Monthly publication volume from database</p>
            <div className="w-full h-[280px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={monthlyData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#64748b' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#64748b' }} />
                  <Tooltip
                    contentStyle={{
                      background: '#fff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                  />
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

        {/* Cluster Table */}
        <div className="bg-white rounded-xl border border-slate-200 p-5">
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
                {clusters.map((c) => (
                  <tr key={c.id} className="border-b border-slate-50 hover:bg-slate-25">
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
                            width: `${topCluster?.paper_count ? (c.paper_count / topCluster.paper_count) * 100 : 0}%`,
                            background: c.color,
                            opacity: 0.8,
                          }}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
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
  icon: React.ComponentType<any>;
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
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <div className="flex items-center justify-between">
        <div className={`w-9 h-9 rounded-lg ${c.bg} flex items-center justify-center`}>
          <Icon size={16} className={c.icon} />
        </div>
        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-50 border border-slate-100 text-slate-500`}>{trend}</span>
      </div>
      <p className="mt-3 text-2xl font-bold text-slate-800">{value}</p>
      <p className="text-xs text-slate-500 mt-0.5">{label}</p>
    </div>
  );
}
