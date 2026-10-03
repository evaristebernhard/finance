import type { LocalAiResponse, ManifestResponse, ReplayResponse, SummaryResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8787";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${body}`);
  }
  return response.json() as Promise<T>;
}

export function fetchManifest(market: string) {
  const params = new URLSearchParams({ market });
  return getJson<ManifestResponse>(`/api/manifest?${params}`);
}

export function fetchReplay(market: string, symbol: string, date: string, offset: number, limit: number, stride: number) {
  const params = new URLSearchParams({
    market,
    symbol,
    date,
    offset: String(offset),
    limit: String(limit),
    stride: String(stride)
  });
  return getJson<ReplayResponse>(`/api/replay?${params}`);
}

export function fetchSummary(market: string, symbol: string, date: string) {
  const params = new URLSearchParams({ market, symbol, date, limit: "120" });
  return getJson<SummaryResponse>(`/api/summary?${params}`);
}

export async function askLocalAi(prompt: string, context: Record<string, unknown>) {
  const response = await fetch("/api/local-ai", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ prompt, context })
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${body}`);
  }
  return response.json() as Promise<LocalAiResponse>;
}
