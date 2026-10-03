import { NextResponse } from "next/server";
import { summaryResponse } from "../../../lib/runner";

export function GET() {
  try {
    return NextResponse.json(summaryResponse());
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
