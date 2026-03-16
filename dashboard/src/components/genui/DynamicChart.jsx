/**
 * GenUI: DynamicChart — Recharts-based dynamic chart rendering.
 */

import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';

const COLORS = ['#6366f1', '#06b6d4', '#f59e0b', '#ef4444', '#10b981', '#8b5cf6'];

// Explicit colors for SVG elements — CSS classes don't reliably set fill/stroke in SVG.
const AXIS_TICK = { fill: '#a1a1aa', fontSize: 12 };
const GRID_STROKE = '#27272a';
const TOOLTIP_STYLE = { backgroundColor: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 };
const TOOLTIP_LABEL = { color: '#e4e4e7' };
const LEGEND_STYLE = { color: '#a1a1aa', fontSize: 12 };

function AutoChart({ chartType, data, config }) {
  const xKey = config.xKey || Object.keys(data[0] || {})[0];
  const yKeys = config.yKeys || Object.keys(data[0] || {}).filter((k) => k !== xKey);

  switch (chartType) {
    case 'bar':
      return (
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
          <XAxis dataKey={xKey} tick={AXIS_TICK} />
          <YAxis tick={AXIS_TICK} />
          <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} />
          <Legend wrapperStyle={LEGEND_STYLE} />
          {yKeys.map((key, i) => (
            <Bar key={key} dataKey={key} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} />
          ))}
        </BarChart>
      );
    case 'area':
      return (
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
          <XAxis dataKey={xKey} tick={AXIS_TICK} />
          <YAxis tick={AXIS_TICK} />
          <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} />
          <Legend wrapperStyle={LEGEND_STYLE} />
          {yKeys.map((key, i) => (
            <Area key={key} dataKey={key} fill={COLORS[i % COLORS.length]} fillOpacity={0.3} stroke={COLORS[i % COLORS.length]} />
          ))}
        </AreaChart>
      );
    case 'pie':
      return (
        <PieChart>
          <Pie data={data} dataKey={yKeys[0]} nameKey={xKey} cx="50%" cy="50%" outerRadius={80} label={{ fill: '#a1a1aa', fontSize: 12 }}>
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} />
          <Legend wrapperStyle={LEGEND_STYLE} />
        </PieChart>
      );
    default:
      return (
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
          <XAxis dataKey={xKey} tick={AXIS_TICK} />
          <YAxis tick={AXIS_TICK} />
          <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} />
          <Legend wrapperStyle={LEGEND_STYLE} />
          {yKeys.map((key, i) => (
            <Line key={key} type="monotone" dataKey={key} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
          ))}
        </LineChart>
      );
  }
}

export default function DynamicChart({ chartType = 'line', data = [], config = {} }) {
  if (!data.length) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg bg-muted text-sm text-muted-foreground">
        No data
      </div>
    );
  }

  const CHART_H = 240; // px — fixed height avoids ResponsiveContainer 0-height measurement bugs

  return (
    <div className="w-full">
      {config.title && <p className="mb-2 text-sm font-medium">{config.title}</p>}
      <ResponsiveContainer width="100%" height={CHART_H}>
        <AutoChart chartType={chartType} data={data} config={config} />
      </ResponsiveContainer>
    </div>
  );
}
