import { fetchJson } from "@/services/api/client";
import { NetworkSnapshot, NetworkStats } from "@/types/api";

export async function getNetworkStats(): Promise<NetworkStats> {
  return fetchJson<NetworkStats>("/api/v1/network/stats", {
    retries: 1,
  });
}

export async function getNetworkSnapshot(): Promise<NetworkSnapshot> {
  return fetchJson<NetworkSnapshot>("/api/v1/network/snapshot", {
    retries: 1,
  });
}

