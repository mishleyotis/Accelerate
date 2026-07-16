/**
 * SSE store — tracks open subscriptions + last-event timestamps so the
 * IntelligencePanel and the Dashboard's active-runs tile can show liveness.
 */
import { create } from "zustand";

interface SseState {
  connected: boolean;
  lastEventAt: number | null;
  channelLastSeen: Record<string, number>;
  setConnected: (b: boolean) => void;
  markEvent: (channel: string) => void;
}

export const useSseStore = create<SseState>((set) => ({
  connected: false,
  lastEventAt: null,
  channelLastSeen: {},
  setConnected: (b) => set({ connected: b }),
  markEvent: (channel) =>
    set((state) => ({
      lastEventAt: Date.now(),
      channelLastSeen: { ...state.channelLastSeen, [channel]: Date.now() },
    })),
}));
