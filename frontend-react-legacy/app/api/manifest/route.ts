import { NextResponse } from "next/server";
import { manifestResponse } from "../../../lib/runner";

export function GET() {
  try {
    return NextResponse.json(manifestResponse());
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
