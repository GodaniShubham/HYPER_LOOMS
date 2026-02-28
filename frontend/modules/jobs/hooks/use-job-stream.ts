"use client";

import { useEffect, useMemo, useState } from "react";

import { wsUrl } from "@/services/api/client";
import { JobLogEntry, JobModel } from "@/types/job";

type JobUpdateEvent = {
  event: "job_update";
  job: JobModel;
};

type JobLogEvent = {
  event: "log";
  job_id: string;
  entry: JobLogEntry;
};

type JobStreamEvent = JobUpdateEvent | JobLogEvent;

type UseJobStreamOptions = {
  jobId?: string;
  onJobUpdate: (job: JobModel) => void;
  onLog: (entry: JobLogEntry) => void;
};

export function useJobStream({ jobId, onJobUpdate, onLog }: UseJobStreamOptions): { connected: boolean } {
  const [connected, setConnected] = useState(false);

  const socketUrl = useMemo(() => {
    if (!jobId) {
      return undefined;
    }
    return wsUrl(`/ws/jobs/${jobId}`);
  }, [jobId]);

  useEffect(() => {
    if (!socketUrl) {
      return;
    }

    let socket: WebSocket | null = null;
    let cancelled = false;
    let reconnectAttempts = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const clearReconnect = () => {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    const scheduleReconnect = () => {
      if (cancelled) {
        return;
      }

      const online = typeof navigator === "undefined" ? true : navigator.onLine;
      const baseDelay = online ? 1300 : 4500;
      const delay = Math.min(10000, baseDelay * Math.max(1, reconnectAttempts + 1));
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

      socket = new WebSocket(socketUrl);

      socket.onopen = () => {
        reconnectAttempts = 0;
        setConnected(true);
      };
      socket.onclose = () => {
        setConnected(false);
        scheduleReconnect();
      };
      socket.onerror = () => setConnected(false);
      socket.onmessage = (message) => {
        try {
          const parsed = JSON.parse(message.data) as JobStreamEvent;
          if (parsed.event === "job_update") {
            onJobUpdate(parsed.job);
          } else if (parsed.event === "log") {
            onLog(parsed.entry);
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

    connect();
    window.addEventListener("online", handleOnline);

    return () => {
      cancelled = true;
      clearReconnect();
      window.removeEventListener("online", handleOnline);
      socket?.close();
    };
  }, [socketUrl, onJobUpdate, onLog]);

  return { connected };
}
