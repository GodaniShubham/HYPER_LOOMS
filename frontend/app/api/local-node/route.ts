import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";

type LocalConfig = {
  node_id?: string | null;
  model_name?: string | null;
  region?: string | null;
  min_vram_gb?: number | null;
};

function resolveConfigPath(): string {
  const appData = process.env.APPDATA || join(homedir(), "AppData", "Roaming");
  return join(appData, "ComputeFabric", "config.json");
}

export async function GET(): Promise<NextResponse> {
  try {
    const configPath = resolveConfigPath();
    const raw = await readFile(configPath, "utf-8");
    const parsed = JSON.parse(raw) as LocalConfig;
    const nodeId = (parsed.node_id || "").trim();

    if (!nodeId) {
      return NextResponse.json({ node: null });
    }

    return NextResponse.json({
      node: {
        id: nodeId,
        gpu: parsed.model_name || "Hyperlooms Local Node",
        vram_total_gb: Math.max(1, Number(parsed.min_vram_gb || 1)),
        vram_used_gb: 0,
        status: "healthy",
        trust_score: 0.9,
        jobs_running: 0,
        latency_ms_avg: 0,
        region: parsed.region || "local",
        model_cache: [],
        last_heartbeat: new Date().toISOString(),
      },
    });
  } catch {
    return NextResponse.json({ node: null });
  }
}
