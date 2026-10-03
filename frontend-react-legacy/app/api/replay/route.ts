import { NextResponse } from "next/server";
import { replayResponse } from "../../../lib/runner";

export function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const offset = Math.max(0, Number(url.searchParams.get("offset") ?? 0));
    const limit = Math.min(3600, Math.max(1, Number(url.searchParams.get("limit") ?? 3600)));
    const stride = Math.max(1, Number(url.searchParams.get("stride") ?? 1));
    return NextResponse.json(replayResponse(offset, limit, stride));
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
