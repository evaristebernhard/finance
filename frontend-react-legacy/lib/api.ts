import type { LocalAiResponse, ManifestResponse, ReplayResponse, SummaryResponse } from "./types";

// The old React surface now talks to the same local Runner artifact as the native
// comparison build. The route handlers do the filesystem work on the server.

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

export function fetchManifest(market: string) {
  return getJson<ManifestResponse>(`/api/manifest?market=${encodeURIComponent(market)}`);
}

export function fetchReplay(market: string, symbol: string, date: string, offset: number, limit: number, stride: number) {
  const params = new URLSearchParams({ market, symbol, date, offset: String(offset), limit: String(limit), stride: String(stride) });
  return getJson<ReplayResponse>(`/api/replay?${params.toString()}`);
}

export function fetchSummary(market: string, symbol: string, date: string) {
  const params = new URLSearchParams({ market, symbol, date });
  return getJson<SummaryResponse>(`/api/summary?${params.toString()}`);
}

export async function askLocalAi(_prompt: string, _context: Record<string, unknown>): Promise<LocalAiResponse> {
  return {
    answer: "这是旧 React workbench 的界面对照模式。当前价格、盘口和 cursor 来自同一个 Runner artifact；右侧下单仍是旧版 toy fill，不代表真实成交链。",
    model: "local comparison stub",
    saved_notes_used: 0
  };
}
