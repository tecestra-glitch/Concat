"use client";
/** React Query hooks for the watch/notify modules (mirrors src/lib/queries.ts for the core API). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSettings } from "@/lib/settings";
import { matchesChange, watchApi, type Change, type ChangeFilters, type EventFilters, type WatchPatch, type WatchStatus } from "@/lib/api/watch";
import type { Mode } from "@/lib/api/client";

export const watchKeys = {
  all: ["watch"] as const,
  statuses: (mode: Mode) => ["watch", "statuses", mode] as const,
  changesAll: (mode: Mode) => ["watch", "changes", mode] as const,
  changes: (mode: Mode, f: ChangeFilters) => ["watch", "changes", mode, f] as const,
  rules: (mode: Mode) => ["alerts", "rules", mode] as const,
  events: (mode: Mode, f: EventFilters) => ["alerts", "events", mode, f] as const,
};

export function useWatchStatuses() {
  const { mode } = useSettings();
  return useQuery({ queryKey: watchKeys.statuses(mode), queryFn: () => watchApi.statuses(mode), refetchInterval: 5_000, staleTime: 2_000 });
}

export function useChanges(f: ChangeFilters = {}) {
  const { mode } = useSettings();
  return useQuery({ queryKey: watchKeys.changes(mode, f), queryFn: () => watchApi.changes(mode, f), refetchInterval: 10_000, staleTime: 5_000 });
}

/** Manual poll with optimistic UI: the row's last/next run move immediately; the Change is prepended on success. */
export function useTriggerPoll() {
  const { mode } = useSettings();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => watchApi.triggerPoll(mode, id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: watchKeys.statuses(mode) });
      const now = Date.now();
      qc.setQueryData<WatchStatus[]>(watchKeys.statuses(mode), (old) =>
        old?.map((s) => (s.source_id === id ? { ...s, last_run_at: new Date(now).toISOString(), next_run_at: new Date(now + s.interval_s * 1000).toISOString() } : s)),
      );
    },
    onSuccess: (change, id) => {
      if (!change) return;
      qc.setQueryData<WatchStatus[]>(watchKeys.statuses(mode), (old) =>
        old?.map((s) => (s.source_id === id ? { ...s, last_change_at: change.ts, changes_24h: s.changes_24h + 1, errors_in_row: 0 } : s)),
      );
      for (const [key, data] of qc.getQueriesData<Change[]>({ queryKey: watchKeys.changesAll(mode) })) {
        const filters = (key[3] ?? {}) as ChangeFilters;
        if (data && matchesChange(change, filters)) qc.setQueryData<Change[]>(key, [change, ...data.filter((c) => c.id !== change.id)]);
      }
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: watchKeys.all }),
  });
}

/** Enable / interval adjustment with optimistic merge; rolled back by the refetch on error. */
export function useUpdateWatch() {
  const { mode } = useSettings();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: WatchPatch }) => watchApi.updateSource(mode, id, patch),
    onMutate: async ({ id, patch }) => {
      await qc.cancelQueries({ queryKey: watchKeys.statuses(mode) });
      qc.setQueryData<WatchStatus[]>(watchKeys.statuses(mode), (old) => old?.map((s) => (s.source_id === id ? { ...s, ...patch } : s)));
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: watchKeys.statuses(mode) }),
  });
}

export function useAlertRules() {
  const { mode } = useSettings();
  return useQuery({ queryKey: watchKeys.rules(mode), queryFn: () => watchApi.rules(mode), staleTime: 30_000 });
}

export function useAlertEvents(f: EventFilters = {}) {
  const { mode } = useSettings();
  return useQuery({ queryKey: watchKeys.events(mode, f), queryFn: () => watchApi.events(mode, f), refetchInterval: 15_000, staleTime: 5_000 });
}
