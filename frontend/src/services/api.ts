/**
 * 后端 API 调用层
 */

export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api';

// ==================== 通用请求 ====================

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

// ==================== 智能问答 ====================

export interface ChatResponse {
  answer: string;
  sources: string[];
  route: string;
  sub_questions: string[];
}

export interface StreamEvent {
  node: string;
  updates: Record<string, any>;
  session_id?: string;
}

export async function chatStream(
  question: string,
  sessionId: string | undefined,
  onEvent: (event: StreamEvent) => void,
  onDone: () => void,
  onError: (error: Error) => void,
  signal?: AbortSignal,
): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, session_id: sessionId }),
      signal,
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No reader');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim();
          if (data === '[DONE]') {
            onDone();
            return;
          }
          try {
            const event = JSON.parse(data);
            onEvent(event);
          } catch {
            // 跳过无法解析的行
          }
        }
      }
    }
    onDone();
  } catch (error) {
    onError(error instanceof Error ? error : new Error(String(error)));
  }
}

// ==================== 知识图谱 ====================

export async function getWikiPages(topic?: string): Promise<{ pages: any[] }> {
  const params = topic ? `?topic=${encodeURIComponent(topic)}` : '';
  return request(`/wiki${params}`);
}

export async function getWikiPage(pageId: number): Promise<any> {
  return request(`/wiki/${pageId}`);
}

export async function updateWikiPage(pageId: number, data: {
  title?: string;
  content?: string;
  topic?: string;
}): Promise<any> {
  return request(`/wiki/${pageId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteWikiPage(pageId: number): Promise<any> {
  return request(`/wiki/${pageId}`, { method: 'DELETE' });
}

export async function getKnowledgeSummaries(limit = 100): Promise<{ summaries: any[] }> {
  return request(`/knowledge?limit=${limit}`);
}

export async function getKnowledgeStats(): Promise<{ total: number; oldest: string; newest: string }> {
  return request('/knowledge/stats');
}

export async function cleanupKnowledge(days = 30): Promise<{ deleted_count: number }> {
  return request(`/knowledge/cleanup?days=${days}`, { method: 'POST' });
}

export async function distillWiki(sessionIds?: string[], topic?: string): Promise<any> {
  return request('/wiki/distill', {
    method: 'POST',
    body: JSON.stringify({ session_ids: sessionIds, topic }),
  });
}

// ==================== 入库管理 ====================

export async function getIngestionFiles(): Promise<{ files: any[] }> {
  return request('/ingestion/files');
}

export async function deleteIngestionFile(sourceFile: string): Promise<any> {
  return request(`/ingestion/files/${encodeURIComponent(sourceFile)}`, { method: 'DELETE' });
}

export async function batchDeleteIngestionFiles(files: string[]): Promise<any> {
  return request('/ingestion/files/batch-delete', {
    method: 'POST',
    body: JSON.stringify({ files }),
  });
}

export async function cleanupDuplicates(): Promise<{ cleaned_count: number }> {
  return request('/ingestion/cleanup-duplicates', { method: 'POST' });
}

// ==================== 原始文件管理 ====================

export async function getRawFiles(): Promise<{ files: any[] }> {
  return request('/files');
}

export async function convertFile(filepath: string): Promise<any> {
  return request('/files/convert', {
    method: 'POST',
    body: JSON.stringify({ filepath }),
  });
}

export async function deleteRawFile(filepath: string): Promise<any> {
  return request(`/files/${encodeURIComponent(filepath)}`, { method: 'DELETE' });
}

export async function previewFile(filepath: string): Promise<{ preview: string; total_length: number }> {
  return request(`/files/${encodeURIComponent(filepath)}/preview`);
}

export async function uploadAndIngest(file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE}/ingest/upload`, { method: 'POST', body: formData });
  if (!response.ok) throw new Error(`API Error: ${response.status}`);
  return response.json();
}

// ==================== 知识图谱 ====================

export interface GraphNode {
  id: string;
  data: {
    label: string;
    type: string;
    description: string;
  };
}

export interface GraphEdge {
  source: string;
  target: string;
  data: {
    label: string;
    description: string;
  };
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export async function getGraph(): Promise<GraphData> {
  return request('/graph');
}

export async function searchGraph(
  query: string,
  entityType?: string,
): Promise<{ results: any[]; count: number }> {
  const params = new URLSearchParams({ q: query });
  if (entityType) params.set('entity_type', entityType);
  return request(`/graph/search?${params}`);
}

export async function getEntityDetail(
  entityType: string,
  entityId: number,
): Promise<{ entity: any; relations: any[] }> {
  return request(`/graph/entity/${entityType}/${entityId}`);
}

// ==================== 知识抽取 ====================

export interface ExtractResponse {
  status: string;
  review_id: number;
  entities: any[];
  relations: any[];
}

export async function extractKnowledge(text: string): Promise<ExtractResponse> {
  return request('/extract', {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
}

export async function extractBatch(): Promise<any> {
  return request('/extract/batch', { method: 'POST' });
}

// ==================== 审核 ====================

export async function getPendingReviews(): Promise<{ items: any[] }> {
  return request('/review/pending');
}

export async function getReviewDetail(reviewId: number): Promise<any> {
  return request(`/review/${reviewId}`);
}

export async function approveReview(
  reviewId: number,
  editedEntities?: any[],
  editedRelations?: any[],
): Promise<any> {
  return request(`/review/${reviewId}/approve`, {
    method: 'POST',
    body: JSON.stringify({
      edited_entities: editedEntities,
      edited_relations: editedRelations,
    }),
  });
}

export async function rejectReview(reviewId: number, reason: string = ''): Promise<any> {
  return request(`/review/${reviewId}/reject?reason=${encodeURIComponent(reason)}`, { method: 'POST' });
}

// ==================== 语料入库 ====================

export async function ingestData(options?: { clear_first?: boolean; force_reingest?: boolean }): Promise<any> {
  return request('/ingest', {
    method: 'POST',
    body: JSON.stringify(options || {}),
  });
}

export async function getStats(): Promise<any> {
  return request('/stats');
}

// ==================== 论文爬虫 ====================

export interface CrawlRequest {
  categories?: string[];
  max_per_keyword?: number;
  download_pdfs?: boolean;
}

export async function crawlPapers(req: CrawlRequest): Promise<any> {
  return request('/crawl', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function getCrawlKeywords(): Promise<Record<string, string[]>> {
  return request('/crawl/keywords');
}

export async function getCrawlResults(): Promise<any> {
  return request('/crawl/results');
}

export async function deleteCrawlResult(index: number): Promise<any> {
  return request(`/crawl/results/${index}`, {
    method: 'DELETE',
  });
}

export async function ingestCrawlResult(index: number): Promise<any> {
  return request(`/crawl/ingest/${index}`, {
    method: 'POST',
  });
}
