/**
 * SERVICE REGISTRY
 * ================
 * Components and hooks import `services` from here and never construct a client
 * themselves. Every service talks to the FastAPI backend at
 * `NEXT_PUBLIC_API_BASE_URL`; there is no in-browser stand-in.
 */

import {
  ApiDashboardService,
  ApiLeadService,
  ApiSearchService,
  ApiWorkspaceService,
} from "./api/api-services";
import type {
  DashboardService,
  LeadService,
  SearchService,
  WorkspaceService,
} from "./types";

type ServiceRegistry = {
  searches: SearchService;
  leads: LeadService;
  dashboard: DashboardService;
  workspace: WorkspaceService;
};

export const services: ServiceRegistry = {
  searches: new ApiSearchService(),
  leads: new ApiLeadService(),
  dashboard: new ApiDashboardService(),
  workspace: new ApiWorkspaceService(),
};

export * from "./types";
