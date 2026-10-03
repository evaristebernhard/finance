import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type { RunConfig, RunEntry, ReplayStateV2, ReplayWindow, ReplayRows, ReplayInspection } from "../types";

export const inTauri = () => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
export async function listRuns(): Promise<RunEntry[]> {
  if (!inTauri()) return [];
  return invoke("list_runs");
}
export const openRun = (runId: string) => invoke<ReplayStateV2>("open_run", {runId});
export const replayCommand = (command: string) => invoke<ReplayStateV2>("replay_command", {command});
export const seek = (fraction: number) => invoke<ReplayStateV2>("seek", {fraction});
// fillId is the fill event ID (not the exchange's fill ID).
export const selectFill = (fillId: string) => invoke<ReplayStateV2>("select_fill", {fillId});
export const startRun = (config: RunConfig) => invoke<ReplayStateV2>("start_run", {config});
export const watchReplay = (onState: (state: ReplayStateV2) => void) => listen<ReplayStateV2>("replay_snapshot_v2", e => onState(e.payload));
export const getReplayWindow = (s: ReplayStateV2, startTsUs: string | null = null, endTsUs: string | null = null) => invoke<ReplayWindow>("get_replay_window", {sessionId: s.sessionId, cursorUpper: s.cursor, startTsUs, endTsUs, maxPoints: 800});
export const queryReplayRows = (s: ReplayStateV2, eventType: string | null, offset: number, limit = 30) => invoke<ReplayRows>("query_replay_rows", {sessionId: s.sessionId, cursorUpper: s.cursor, eventType, offset, limit});
export const inspectReplayEvent = (s: ReplayStateV2, eventId: string) => invoke<ReplayInspection>("inspect_replay_event", {sessionId: s.sessionId, cursorUpper: s.cursor, eventId});
