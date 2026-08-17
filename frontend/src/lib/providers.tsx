"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toast, Tooltip } from "radix-ui";
import { useState, type ReactNode } from "react";
import { ThemeProvider } from "./theme-provider";
import { ToastProvider } from "@/components/ui/toast";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Progress endpoints are polled; everything else stays warm briefly.
            staleTime: 10_000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <Tooltip.Provider delayDuration={220}>
          <Toast.Provider swipeDirection="right" duration={3200}>
            <ToastProvider>{children}</ToastProvider>
          </Toast.Provider>
        </Tooltip.Provider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
