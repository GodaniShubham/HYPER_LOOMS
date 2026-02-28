"use client";

import { useEffect, useState } from "react";

import { wsUrl } from "@/services/api/client";
import { NetworkSnapshot } from "@/types/api";

type NetworkUpdateEvent = {
  event: "network_update";
  snapshot: NetworkSnapshot;
};

export function useNetworkStream(
  onNetworkUpdate: (snapshot: NetworkSnapshot) => void
): { connected: boolean } {
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let cancelled = false;
    let reconnectAttempts = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let flushTimer: ReturnType<typeof setTimeout> | null = null;
    let pendingSnapshot: NetworkSnapshot | null = null;
    let lastEmitAt = 0;

    const closeSocket = () => {
      const current = socket;
      if (!current) {
        return;
      }
      socket = null;

      // Strict-mode remounts can clean up before the handshake finishes.
      // Delay close until open to avoid noisy "closed before established" warnings.
      if (current.readyState === WebSocket.CONNECTING) {
        current.addEventListener(
          "open",
          () => {
            current.close(1000, "cleanup");
          },
          { once: true }
        );
        return;
      }

      if (current.readyState === WebSocket.OPEN) {
        current.close(1000, "cleanup");
      }
    };

    const clearReconnect = () => {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    const clearFlush = () => {
      if (flushTimer) {
        clearTimeout(flushTimer);
        flushTimer = null;
      }
      pendingSnapshot = null;
    };

    const emitSnapshot = (snapshot: NetworkSnapshot) => {
      lastEmitAt = Date.now();
      onNetworkUpdate(snapshot);
    };

    const queueSnapshot = (snapshot: NetworkSnapshot) => {
      const elapsed = Date.now() - lastEmitAt;
      if (elapsed >= 700 && !flushTimer) {
        emitSnapshot(snapshot);
        return;
      }

      pendingSnapshot = snapshot;
      if (flushTimer) {
        return;
      }

      const wait = Math.max(120, 700 - elapsed);
      flushTimer = setTimeout(() => {
        flushTimer = null;
        if (!pendingSnapshot) {
          return;
        }
        const latest = pendingSnapshot;
        pendingSnapshot = null;
        emitSnapshot(latest);
      }, wait);
    };

    const scheduleReconnect = () => {
      if (cancelled) {
        return;
      }

      const online = typeof navigator === "undefined" ? true : navigator.onLine;
      const visible = typeof document === "undefined" ? true : document.visibilityState === "visible";
      const baseDelay = online ? (visible ? 1200 : 3500) : 5000;
      const delay = Math.min(12000, baseDelay * Math.max(1, reconnectAttempts + 1));
      reconnectAttempts += 1;

      clearReconnect();
      reconnectTimer = setTimeout(connect, delay);
    };

    const connect = () => {
      if (cancelled) {
        return;
      }

      const online = typeof navigator === "undefined" ? true : navigator.onLine;
      if (!online) {
        setConnected(false);
        scheduleReconnect();
        return;
      }

      const nextSocket = new WebSocket(wsUrl("/ws/network"));
      socket = nextSocket;

      nextSocket.onopen = () => {
        if (cancelled || socket !== nextSocket) {
          nextSocket.close(1000, "stale");
          return;
        }
        reconnectAttempts = 0;
        setConnected(true);
      };
      nextSocket.onclose = (event) => {
        if (cancelled || socket !== nextSocket) {
          return;
        }
        setConnected(false);
        if (event.code === 1000 && event.reason === "cleanup") {
          return;
        }
        scheduleReconnect();
      };
      nextSocket.onerror = () => {
        if (!cancelled && socket === nextSocket) {
          setConnected(false);
        }
      };
      nextSocket.onmessage = (message) => {
        try {
          const parsed = JSON.parse(message.data) as NetworkUpdateEvent;
          if (parsed.event === "network_update") {
            queueSnapshot(parsed.snapshot);
          }
        } catch {
          // ignore malformed payloads
        }
      };
    };

    const handleOnline = () => {
      if (cancelled) {
        return;
      }
      const state = socket?.readyState;
      if (state === WebSocket.OPEN || state === WebSocket.CONNECTING) {
        return;
      }
      connect();
    };

    const handleVisibility = () => {
      if (document.visibilityState !== "visible") {
        return;
      }
      const state = socket?.readyState;
      if (state === WebSocket.OPEN || state === WebSocket.CONNECTING) {
        return;
      }
      connect();
    };

    connect();
    window.addEventListener("online", handleOnline);
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      cancelled = true;
      clearReconnect();
      clearFlush();
      window.removeEventListener("online", handleOnline);
      document.removeEventListener("visibilitychange", handleVisibility);
      closeSocket();
    };
  }, [onNetworkUpdate]);

  return { connected };
}
