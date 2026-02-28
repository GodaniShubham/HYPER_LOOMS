import { create } from "zustand";

type UiState = {
  selectedJobId?: string;
  setSelectedJobId: (id?: string) => void;
};

export const useUiStore = create<UiState>((set) => ({
  selectedJobId: undefined,
  setSelectedJobId: (id) => set({ selectedJobId: id }),
}));

