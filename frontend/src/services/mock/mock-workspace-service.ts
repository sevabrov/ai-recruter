import type { HealthStatus, WorkspaceService } from "@/services/types";
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
      providers: { braveSearch: false, scrapegraph: false, openai: false },
    };
  }

  async reset(): Promise<void> {
    await latency(120);
    resetMockState();
  }
}
