"use client";

import { Toast } from "radix-ui";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { Tone } from "@/lib/domain";
import { cn } from "@/lib/utils";
import { Dot } from "./badge";

type ToastItem = {
  id: number;
  title: string;
  description?: string;
  tone: Tone;
};

type ToastContextValue = {
  toast: (input: { title: string; description?: string; tone?: Tone }) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

/** Must sit inside Radix's <Toast.Provider> — see src/lib/providers.tsx. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback<ToastContextValue["toast"]>(({ title, description, tone = "accent" }) => {
    setItems((current) => [...current, { id: Date.now() + current.length, title, description, tone }]);
  }, []);

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {items.map((item) => (
        <Toast.Root
          key={item.id}
          onOpenChange={(open) =>
            !open && setItems((current) => current.filter((entry) => entry.id !== item.id))
          }
          className={cn(
            "card flex items-start gap-3 px-4 py-3 shadow-pop",
            "data-[state=open]:animate-fade-up data-[swipe=end]:opacity-0",
          )}
        >
          <span className="mt-1.5">
            <Dot tone={item.tone} />
          </span>
          <div className="min-w-0">
            <Toast.Title className="text-sm font-medium">{item.title}</Toast.Title>
            {item.description ? (
              <Toast.Description className="mt-0.5 text-xs text-fg-muted">
                {item.description}
              </Toast.Description>
            ) : null}
          </div>
        </Toast.Root>
      ))}
      <Toast.Viewport className="fixed right-5 bottom-5 z-100 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2 outline-none" />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside <ToastProvider>");
  return context;
}
