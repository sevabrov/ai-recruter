import type { HealthStatus, SourcesReport, WorkspaceService } from "@/services/types";
import { latency, resetMockState } from "./mock-db";

/** The mock data source is always "reachable" — it is this browser tab. */
export class MockWorkspaceService implements WorkspaceService {
  async health(): Promise<HealthStatus> {
    await latency(60);
    return {
      status: "ok",
      service: "in-browser fixtures",
      version: "1.0.0",
      phase: 1,
      pipeline: "fixture",
      storage: "browser",
      stages: { search: "fixture", extraction: "fixture", signals: "fixture" },
      providers: { braveSearch: false, scrapegraph: false, openai: false },
    };
  }

  /**
   * Nothing is ever read in mock mode, so the record is empty — which is the
   * honest answer, and the same one the backend gives before its first live run.
   */
  async sources(): Promise<SourcesReport> {
    await latency(60);
    return {
      reader: "fixture",
      live: false,
      cacheTtlHours: 168,
      fallback: "No page is fetched: profiles come from the fixtures themselves.",
      items: [],
    };
  }

  async reset(): Promise<void> {
    await latency(120);
    resetMockState();
  }
}
