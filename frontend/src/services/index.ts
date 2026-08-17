/**
 * SERVICE REGISTRY
 * ================
 * The single switch between Phase 1 and Phase 2. Components and hooks import
 * `services` from here and never know which implementation answers.
 *
 *   NEXT_PUBLIC_DATA_SOURCE=mock   (default) → in-browser fixtures
 *   NEXT_PUBLIC_DATA_SOURCE=api              → FastAPI backend
 */

import {
  ApiDashboardService,
  ApiLeadService,
  ApiSearchService,
} from "./api/api-services";
import { MockDashboardService } from "./mock/mock-dashboard-service";
import { MockLeadService } from "./mock/mock-lead-service";
import { MockSearchService } from "./mock/mock-search-service";
import type { DashboardService, LeadService, SearchService } from "./types";

export type DataSource = "mock" | "api";

export const DATA_SOURCE: DataSource =
  process.env.NEXT_PUBLIC_DATA_SOURCE === "api" ? "api" : "mock";

export const IS_MOCK = DATA_SOURCE === "mock";

type ServiceRegistry = {
  searches: SearchService;
  leads: LeadService;
  dashboard: DashboardService;
};

export const services: ServiceRegistry =
  DATA_SOURCE === "api"
    ? {
        searches: new ApiSearchService(),
        leads: new ApiLeadService(),
        dashboard: new ApiDashboardService(),
      }
    : {
        searches: new MockSearchService(),
        leads: new MockLeadService(),
        dashboard: new MockDashboardService(),
      };

export * from "./types";
