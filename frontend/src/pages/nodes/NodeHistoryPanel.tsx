import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { HttpUtil } from '@/utils';
import { Sparkline } from '@/components/viz';
import './NodeHistoryPanel.css';

interface NodeRef {
  id: number;
}

interface NodeHistoryPanelProps {
  node: NodeRef;
  bucket?: number;
}

interface SeriesPoint {
  t: number;
  v: number;
}

interface ApiMsg<T = unknown> {
  success?: boolean;
  obj?: T;
}

const REFRESH_MS = 15000;

const formatKbps = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 1 });

export default function NodeHistoryPanel({ node, bucket = 30 }: NodeHistoryPanelProps) {
  const { t } = useTranslation();
  const key = `${node.id}/${bucket}`;
  const [history, setHistory] = useState<{
    key: string;
    series: { vals: number[]; labs: string[] }[];
    failed: boolean;
  } | null>(null);
  const current = history?.key === key ? history : null;
  const empty = { vals: [], labs: [] };
  const [cpu = empty, mem = empty, netUp = empty, netDown = empty] = current?.series ?? [];

  useEffect(() => {
    const request = new AbortController();
    let timer: number | undefined;

    const bucketLabel = (unixSec: number) => {
      const d = new Date(unixSec * 1000);
      const hh = String(d.getHours()).padStart(2, '0');
      const mm = String(d.getMinutes()).padStart(2, '0');
      if (bucket >= 60) return `${hh}:${mm}`;
      const ss = String(d.getSeconds()).padStart(2, '0');
      return `${hh}:${mm}:${ss}`;
    };

    // cpu/mem are percentages (clamp 0-100); net throughput is bytes/sec shown
    // as KB/s, which must opt out of Sparkline's 0-100 "%" defaults.
    const fetchSeries = async (metric: string, kind: 'pct' | 'rate') => {
      try {
        const url = `/panel/api/nodes/history/${node.id}/${metric}/${bucket}`;
        const msg = (await HttpUtil.get(url, undefined, {
          silent: true, signal: request.signal, timeout: REFRESH_MS,
        })) as ApiMsg<SeriesPoint[]>;
        if (msg?.success && Array.isArray(msg.obj)) {
          const vals: number[] = [];
          const labs: string[] = [];
          for (const p of msg.obj) {
            labs.push(bucketLabel(p.t));
            const n = Number(p.v) || 0;
            vals.push(kind === 'pct' ? Math.max(0, Math.min(100, n)) : Math.max(0, n / 1024));
          }
          return { vals, labs };
        }
      } catch {
        // Leave the last complete snapshot visible while the connection recovers.
      }
      return null;
    };

    const refresh = async () => {
      const series = await Promise.all([
        fetchSeries('cpu', 'pct'),
        fetchSeries('mem', 'pct'),
        fetchSeries('netUp', 'rate'),
        fetchSeries('netDown', 'rate'),
      ]);
      if (request.signal.aborted) return;
      if (series.every((points) => points !== null)) {
        setHistory({ key, series, failed: false });
      } else {
        setHistory((previous) => ({
          key, series: previous?.key === key ? previous.series : [], failed: true,
        }));
      }
      // Schedule from completion so an earlier response cannot overwrite a later refresh.
      timer = window.setTimeout(refresh, REFRESH_MS);
    };

    void refresh();
    return () => {
      request.abort();
      window.clearTimeout(timer);
    };
  }, [node.id, bucket, key]);

  return (
    <div className="node-history-panel">
      {current?.failed && <div className="node-history-status" role="status">{t('somethingWentWrong')}</div>}
      <div className="series">
        <div className="series-title">{t('pages.nodes.cpu')}</div>
        <Sparkline
          data={cpu.vals}
          labels={cpu.labs}
          height={120}
          stroke="#008771"
          showGrid
          showAxes
          tickCountX={4}
          maxPoints={cpu.vals.length || 1}
          fillOpacity={0.18}
          markerRadius={2.6}
          showTooltip
        />
      </div>
      <div className="series">
        <div className="series-title">{t('pages.nodes.mem')}</div>
        <Sparkline
          data={mem.vals}
          labels={mem.labs}
          height={120}
          stroke="#7c4dff"
          showGrid
          showAxes
          tickCountX={4}
          maxPoints={mem.vals.length || 1}
          fillOpacity={0.18}
          markerRadius={2.6}
          showTooltip
        />
      </div>
      <div className="series">
        <div className="series-title">{t('pages.nodes.netUp')}</div>
        <Sparkline
          data={netUp.vals}
          labels={netUp.labs}
          height={120}
          stroke="#1677ff"
          showGrid
          showAxes
          tickCountX={4}
          maxPoints={netUp.vals.length || 1}
          fillOpacity={0.18}
          markerRadius={2.6}
          showTooltip
          valueMax={null}
          yFormatter={formatKbps}
        />
      </div>
      <div className="series">
        <div className="series-title">{t('pages.nodes.netDown')}</div>
        <Sparkline
          data={netDown.vals}
          labels={netDown.labs}
          height={120}
          stroke="#fa8c16"
          showGrid
          showAxes
          tickCountX={4}
          maxPoints={netDown.vals.length || 1}
          fillOpacity={0.18}
          markerRadius={2.6}
          showTooltip
          valueMax={null}
          yFormatter={formatKbps}
        />
      </div>
    </div>
  );
}
