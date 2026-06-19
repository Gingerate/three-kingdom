import { useEffect, useRef, useState, useCallback } from 'react';
import { Input, Select, Spin, Drawer, Descriptions, Tag, Empty, Button, message } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import { Graph } from '@antv/g6';
import { getGraph, searchGraph, getEntityDetail, getCoverage, type GraphData } from '../services/api';

const { Search } = Input;

/** 读取 CSS 变量的计算颜色值（用于 G6 等不支持 CSS 变量的库） */
function getCSSColor(varName: string): string {
  const val = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  return val || '#999';
}

const ENTITY_COLORS: Record<string, string> = {
  person: getCSSColor('--color-accent'),
  event: getCSSColor('--color-green'),
  force: getCSSColor('--color-bronze'),
};

const ENTITY_LABELS: Record<string, string> = {
  person: '人物',
  event: '事件',
  force: '势力',
};

/** 实体详情接口 */
interface EntityDetail {
  id: number;
  name: string;
  entity_type: string;
  description?: string;
  courtesy_name?: string;
  origin?: string;
  birth_year?: string;
  death_year?: string;
  year?: string;
  location?: string;
  leader?: string;
  period?: string;
}

/** 关系详情接口 */
interface RelationDetail {
  id: number;
  source_type: string;
  source_id: number;
  source_name?: string;
  target_type: string;
  target_id: number;
  target_name?: string;
  relation_type: string;
}

export default function GraphPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);
  const [loading, setLoading] = useState(true);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [filterType, setFilterType] = useState<string | undefined>(undefined);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState<EntityDetail | null>(null);
  const [selectedRelations, setSelectedRelations] = useState<RelationDetail[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [coverage, setCoverage] = useState<{
    entities: { persons: number; events: number; forces: number; total: number };
    relations: number;
    coverage: { persons_with_description: number; events_with_description: number };
    wiki_pages: number;
    knowledge_summaries: number;
  } | null>(null);

  const loadGraph = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getGraph();
      setGraphData(data);
      renderGraph(data);
    } catch (error) {
      message.error('加载图谱失败，请确保后端已启动');
    } finally {
      setLoading(false);
    }
  }, []);

  const renderGraph = (data: GraphData) => {
    if (!containerRef.current) return;
    if (graphRef.current) {
      graphRef.current.destroy();
      graphRef.current = null;
    }
    if (data.nodes.length === 0) return;

    const graph = new Graph({
      container: containerRef.current,
      autoFit: 'view',
      data: {
        nodes: data.nodes.map((n) => ({ id: n.id, data: { ...n.data } })),
        edges: data.edges.map((e, i) => ({
          id: `edge_${i}`,
          source: e.source,
          target: e.target,
          data: { ...e.data },
        })),
      },
      node: {
        style: {
          size: (d: any) => {
            const sizes: Record<string, number> = { person: 38, event: 32, force: 42 };
            const base = sizes[d.data?.type as string] || 38;
            return d.data?._highlighted ? base * 1.3 : base;
          },
          fill: (d: any) => {
            if (d.data?._highlighted) return getCSSColor('--color-accent');
            return ENTITY_COLORS[d.data?.type] || '#999';
          },
          stroke: (d: any) => d.data?._highlighted ? getCSSColor('--color-accent') : getCSSColor('--color-paper'),
          lineWidth: (d: any) => d.data?._highlighted ? 3 : 2,
          labelText: (d: any) => d.data?.label || d.id,
          labelFontSize: 12,
          labelFill: getCSSColor('--color-ink'),
          labelFontFamily: '"LXGW WenKai", serif',
          labelPlacement: 'bottom',
          labelOffsetY: 5,
          cursor: 'pointer',
        },
      },
      edge: {
        style: {
          endArrow: true,
          stroke: getCSSColor('--color-rule'),
          lineWidth: 1.5,
          labelText: (d: any) => d.data?.label || '',
          labelFontSize: 10,
          labelFill: getCSSColor('--color-ink-3'),
          labelBackground: true,
          labelBackgroundFill: getCSSColor('--color-paper'),
          labelBackgroundOpacity: 0.9,
          labelPadding: [2, 4],
        },
      },
      layout: {
        type: 'd3-force',
        preventOverlap: true,
        nodeSize: 60,
        linkDistance: 150,
        nodeStrength: -300,
      },
      behaviors: ['drag-element', 'zoom-canvas', 'drag-canvas'],
    });

    let currentRequestId = 0;

    graph.on('node:click', async (event: any) => {
      const nodeId = event.target?.id;
      if (!nodeId) return;
      const parts = nodeId.split('_');
      const entityType = parts[0];
      const entityId = parseInt(parts[1]);
      if (!entityType || isNaN(entityId)) return;

      const requestId = ++currentRequestId;
      setDrawerOpen(true);
      setDetailLoading(true);
      setSelectedEntity(null);
      setSelectedRelations([]);

      try {
        const detail = await getEntityDetail(entityType, entityId);
        // 快速点击多个节点时，只采纳最后一次请求的结果
        if (requestId !== currentRequestId) return;
        setSelectedEntity({ ...detail.entity, entity_type: entityType });
        setSelectedRelations(detail.relations || []);
      } catch {
        if (requestId !== currentRequestId) return;
        message.error('获取详情失败');
      } finally {
        if (requestId === currentRequestId) {
          setDetailLoading(false);
        }
      }
    });

    graph.render();
    graphRef.current = graph;
  };

  useEffect(() => {
    loadGraph();
    getCoverage().then(setCoverage).catch(() => {});
    return () => {
      if (graphRef.current) {
        graphRef.current.destroy();
        graphRef.current = null;
      }
    };
  }, [loadGraph]);

  const handleSearch = async (value: string) => {
    if (!value.trim()) {
      if (graphData) renderGraph(graphData);
      return;
    }
    setLoading(true);
    try {
      const result = await searchGraph(value, filterType);
      if (result.count === 0) {
        message.info('未找到匹配的实体');
        setLoading(false);
        return;
      }
      if (graphData) {
        const matchIds = new Set(result.results.map((r: any) => `${r.entity_type}_${r.id}`));
        renderGraph({
          nodes: graphData.nodes.map((n) => ({
            ...n,
            data: { ...n.data, _highlighted: matchIds.has(n.id) },
          })),
          edges: graphData.edges,
        });
      }
    } catch {
      message.error('搜索失败');
    } finally {
      setLoading(false);
    }
  };

  const handleFilterChange = (value: string | undefined) => {
    setFilterType(value);
    if (graphData) {
      const nodes = value
        ? graphData.nodes.filter((n) => n.data.type === value)
        : graphData.nodes;
      const ids = new Set(nodes.map((n) => n.id));
      renderGraph({
        nodes,
        edges: graphData.edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
      });
    }
  };

  // 统计数据
  const stats = graphData ? {
    totalNodes: graphData.nodes.length,
    totalEdges: graphData.edges.length,
    personCount: graphData.nodes.filter(n => n.data.type === 'person').length,
    eventCount: graphData.nodes.filter(n => n.data.type === 'event').length,
    forceCount: graphData.nodes.filter(n => n.data.type === 'force').length,
  } : null;

  return (
    <div className="page-shell">
      {/* 工具栏 */}
      <div className="page-header">
        <span className="page-header-title">知识图谱</span>
        <div className="page-header-spacer" />
        <Select
          placeholder="筛选类型"
          allowClear
          style={{ width: 110 }}
          onChange={handleFilterChange}
          options={[
            { value: 'person', label: '人物' },
            { value: 'event', label: '事件' },
            { value: 'force', label: '势力' },
          ]}
        />
        <Search
          placeholder="搜索实体"
          allowClear
          style={{ width: 180 }}
          onSearch={handleSearch}
          enterButton={<SearchOutlined />}
        />
        <Button icon={<ReloadOutlined />} onClick={loadGraph} />
      </div>

      {/* 统计卡片 */}
      {stats && (
        <div className="graph-stats-bar">
          <div className="graph-stat-item">
            <span className="graph-stat-value">{stats.totalNodes}</span>
            <span className="graph-stat-label">实体总数</span>
          </div>
          <div className="graph-stat-divider" />
          <div className="graph-stat-item">
            <span className="graph-stat-value" style={{ color: ENTITY_COLORS.person }}>{stats.personCount}</span>
            <span className="graph-stat-label">人物</span>
          </div>
          <div className="graph-stat-item">
            <span className="graph-stat-value" style={{ color: ENTITY_COLORS.event }}>{stats.eventCount}</span>
            <span className="graph-stat-label">事件</span>
          </div>
          <div className="graph-stat-item">
            <span className="graph-stat-value" style={{ color: ENTITY_COLORS.force }}>{stats.forceCount}</span>
            <span className="graph-stat-label">势力</span>
          </div>
          <div className="graph-stat-divider" />
          <div className="graph-stat-item">
            <span className="graph-stat-value">{stats.totalEdges}</span>
            <span className="graph-stat-label">关系</span>
          </div>
          {coverage && (
            <>
              <div className="graph-stat-divider" />
              <div className="graph-stat-item">
                <span className="graph-stat-value">{coverage.wiki_pages}</span>
                <span className="graph-stat-label">Wiki</span>
              </div>
              <div className="graph-stat-item">
                <span className="graph-stat-value">{coverage.knowledge_summaries}</span>
                <span className="graph-stat-label">知识摘要</span>
              </div>
            </>
          )}
        </div>
      )}

      {/* 图谱 */}
      <div ref={containerRef} style={{ flex: 1, position: 'relative', minHeight: 0 }}>
        {loading && (
          <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }}>
            <Spin size="large" />
          </div>
        )}
        {!loading && graphData && graphData.nodes.length === 0 && (
          <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }}>
            <Empty description="暂无图谱数据，请先入库并抽取实体" />
          </div>
        )}
      </div>

      {/* 详情抽屉 */}
      <Drawer
        title={selectedEntity?.name || '实体详情'}
        placement="right"
        width={380}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        className="themed-drawer"
      >
        {detailLoading ? (
          <Spin />
        ) : selectedEntity ? (
          <>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="类型">
                <Tag color={ENTITY_COLORS[selectedEntity.entity_type]}>
                  {ENTITY_LABELS[selectedEntity.entity_type] || selectedEntity.entity_type}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="名称">{selectedEntity.name}</Descriptions.Item>
              {selectedEntity.description && <Descriptions.Item label="描述">{selectedEntity.description}</Descriptions.Item>}
              {selectedEntity.courtesy_name && <Descriptions.Item label="字">{selectedEntity.courtesy_name}</Descriptions.Item>}
              {selectedEntity.origin && <Descriptions.Item label="籍贯">{selectedEntity.origin}</Descriptions.Item>}
              {selectedEntity.birth_year && <Descriptions.Item label="生年">{selectedEntity.birth_year}</Descriptions.Item>}
              {selectedEntity.death_year && <Descriptions.Item label="卒年">{selectedEntity.death_year}</Descriptions.Item>}
              {selectedEntity.year && <Descriptions.Item label="年份">{selectedEntity.year}</Descriptions.Item>}
              {selectedEntity.location && <Descriptions.Item label="地点">{selectedEntity.location}</Descriptions.Item>}
              {selectedEntity.leader && <Descriptions.Item label="领袖">{selectedEntity.leader}</Descriptions.Item>}
              {selectedEntity.period && <Descriptions.Item label="时期">{selectedEntity.period}</Descriptions.Item>}
            </Descriptions>
            {selectedRelations.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <h4 style={{ fontSize: 14, marginBottom: 8, color: 'var(--color-ink-2)' }}>
                  相关关系（{selectedRelations.length}）
                </h4>
                {selectedRelations.map((rel, i) => (
                  <Tag key={i} style={{ margin: '3px', fontSize: 12 }}>
                    {rel.source_name || `${rel.source_type}:${rel.source_id}`} → {rel.relation_type} → {rel.target_name || `${rel.target_type}:${rel.target_id}`}
                  </Tag>
                ))}
              </div>
            )}
          </>
        ) : (
          <Empty description="点击节点查看详情" />
        )}
      </Drawer>

    </div>
  );
}
