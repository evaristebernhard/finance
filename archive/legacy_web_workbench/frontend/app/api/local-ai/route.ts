import { NextResponse } from "next/server";
import { appendFile, mkdir, readFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { dirname, join } from "node:path";
import { homedir } from "node:os";

const LOCAL_AI_BASE = process.env.LOCAL_AI_BASE ?? "http://127.0.0.1:32081/v1";
const LOCAL_AI_MODEL = process.env.LOCAL_AI_MODEL ?? "gpt-5.5";
const NOTE_FILE = process.env.REPLAY_AI_NOTES_PATH
  ?? join(process.cwd(), "..", "data", "market_replay", "_work", "replay_ai_notes.jsonl");

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await request.json() as { prompt?: string; context?: unknown };
    const prompt = String(body.prompt ?? "").trim();
    if (!prompt) {
      return NextResponse.json({ error: "empty prompt" }, { status: 400 });
    }
    const context = body.context ?? {};
    const savedNotes = await relevantNotes(context, 8);

    const localKey = await localAiKey();
    const headers: Record<string, string> = { "content-type": "application/json" };
    if (localKey) {
      headers.authorization = `Bearer ${localKey}`;
      headers["x-api-key"] = localKey;
    }

    const response = await fetch(`${LOCAL_AI_BASE.replace(/\/$/, "")}/chat/completions`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        model: LOCAL_AI_MODEL,
        temperature: 0.2,
        messages: [
          {
            role: "system",
            content: [
              "You are a local quant-replay assistant inside a multi-market order-book replay workbench.",
              "Explain factor/price/volatility relationships conservatively.",
              "Do not give live trading advice, entry instructions, or sizing.",
              "Focus on whether the visible evidence is interpretable, noisy, lagging, or cost-constrained.",
              "Answer in Chinese with readable Markdown: short sections and paragraphs are fine.",
              "Use bullets only when they reduce ambiguity; avoid wide markdown tables and column-style layouts.",
              "Use LaTeX for formulas when helpful, preferably inline unless a displayed formula is genuinely clearer."
            ].join(" ")
          },
          {
            role: "user",
            content: JSON.stringify({
              question: prompt,
              context,
              saved_notes_recent: savedNotes.map((note) => ({
                created_at: note.created_at,
                question: note.question,
                answer: note.answer,
                context: note.context
              }))
            })
          }
        ],
        max_completion_tokens: 900
      }),
      cache: "no-store"
    });

    if (!response.ok) {
      const text = await response.text();
      return NextResponse.json({ error: sanitizeAiError(text || response.statusText) }, { status: response.status });
    }

    const json = await response.json();
    const answer = json?.choices?.[0]?.message?.content ?? json?.output_text ?? "";
    const model = json?.model ?? LOCAL_AI_MODEL;
    const note = {
      id: randomUUID(),
      created_at: new Date().toISOString(),
      question: prompt,
      answer,
      model,
      context: compactContext(context)
    };
    let saveError = "";
    try {
      await appendNote(note);
    } catch (error) {
      saveError = error instanceof Error ? error.message : "save failed";
    }
    return NextResponse.json({
      answer,
      model,
      note_id: note.id,
      saved_notes_used: savedNotes.length,
      save_error: saveError
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "local AI request failed" },
      { status: 500 }
    );
  }
}

type AiNote = {
  id: string;
  created_at: string;
  question: string;
  answer: string;
  model?: string;
  context?: Record<string, unknown>;
};

async function appendNote(note: AiNote) {
  await mkdir(dirname(NOTE_FILE), { recursive: true });
  await appendFile(NOTE_FILE, `${JSON.stringify(note)}\n`, "utf8");
}

async function relevantNotes(context: unknown, limit: number): Promise<AiNote[]> {
  const notes = await readNotes();
  if (notes.length === 0) return [];
  const current = compactContext(context);
  return notes
    .map((note, idx) => ({ note, idx, score: noteScore(note, current) }))
    .sort((a, b) => b.score - a.score || b.idx - a.idx)
    .slice(0, limit)
    .map((item) => item.note);
}

async function readNotes(): Promise<AiNote[]> {
  try {
    const raw = await readFile(NOTE_FILE, "utf8");
    return raw
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => {
        try {
          return JSON.parse(line) as AiNote;
        } catch {
          return null;
        }
      })
      .filter((note): note is AiNote => Boolean(note))
      .slice(-200);
  } catch {
    return [];
  }
}

function noteScore(note: AiNote, current: Record<string, unknown>) {
  const saved = note.context ?? {};
  let score = 0;
  if (saved.symbol && saved.symbol === current.symbol) score += 8;
  if (saved.date && saved.date === current.date) score += 4;
  if (saved.selectedFactor && saved.selectedFactor === current.selectedFactor) score += 6;
  if (saved.factorLabel && saved.factorLabel === current.factorLabel) score += 2;
  return score;
}

function compactContext(context: unknown): Record<string, unknown> {
  if (!context || typeof context !== "object") return {};
  const record = context as Record<string, unknown>;
  const keys = [
    "symbol",
    "date",
    "timestamp",
    "offset",
    "selectedFactor",
    "factorLabel",
    "factorValue",
    "price",
    "bestBid",
    "bestAsk",
    "spreadBps",
    "volatilityForecastBps",
    "realizedVolBps",
    "dlogStBps",
    "tickSize",
    "feeHurdleTicks",
    "meanAbsNextMoveTicks",
    "pAbsMoveGtFee",
    "pearsonCurrentReturn",
    "pearsonNextReturn",
    "pearsonAbsNextReturn",
    "lagCorrs",
    "panelMidDeltaBps"
  ];
  return Object.fromEntries(keys.filter((key) => key in record).map((key) => [key, record[key]]));
}

async function localAiKey() {
  if (process.env.LOCAL_AI_API_KEY) return process.env.LOCAL_AI_API_KEY;
  try {
    const raw = await readFile(join(homedir(), ".codex", "auth.json"), "utf8");
    const parsed = JSON.parse(raw) as unknown;
    return findOpenAiKey(parsed) ?? "";
  } catch {
    return "";
  }
}

function findOpenAiKey(value: unknown): string | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  const direct = record.OPENAI_API_KEY;
  if (typeof direct === "string" && direct.trim()) return direct.trim();
  for (const child of Object.values(record)) {
    const found = findOpenAiKey(child);
    if (found) return found;
  }
  return undefined;
}

function sanitizeAiError(value: string) {
  return value
    .replace(/sk-[A-Za-z0-9_-]{12,}/g, "[redacted-key]")
    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]{12,}/gi, "Bearer [redacted]")
    .slice(0, 2000);
}
