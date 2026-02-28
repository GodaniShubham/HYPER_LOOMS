import { create } from "zustand";

import { JobConfig } from "@/types/job";

type JobDraftState = {
  prompt: string;
  config: JobConfig;
  setPrompt: (prompt: string) => void;
  setConfig: (patch: Partial<JobConfig>) => void;
  reset: () => void;
};

const defaultConfig: JobConfig = {
  model: "fabric-workload-v1",
  provider: "fabric",
  replicas: 2,
  max_tokens: 512,
  temperature: 0.3,
  preferred_region: null,
};

export const useJobDraftStore = create<JobDraftState>((set) => ({
  prompt: "",
  config: defaultConfig,
  setPrompt: (prompt) => set({ prompt }),
  setConfig: (patch) =>
    set((state) => ({
      config: {
        ...state.config,
        ...patch,
      },
    })),
  reset: () => set({ prompt: "", config: defaultConfig }),
}));

