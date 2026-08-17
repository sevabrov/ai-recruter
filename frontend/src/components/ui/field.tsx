"use client";

import { Label } from "radix-ui";
import { forwardRef, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const CONTROL =
  "w-full rounded-ctl border border-line bg-surface px-3 text-sm text-fg placeholder:text-fg-faint " +
  "transition-colors hover:border-line-strong focus:border-accent focus:outline-none " +
  "focus-visible:outline-none disabled:opacity-50";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return <input ref={ref} className={cn(CONTROL, "h-9.5 py-2", className)} {...props} />;
  },
);

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return (
      <textarea
        ref={ref}
        className={cn(CONTROL, "min-h-20 resize-y py-2 leading-relaxed", className)}
        {...props}
      />
    );
  },
);

export function Field({
  label,
  hint,
  optional,
  htmlFor,
  children,
  className,
}: {
  label: string;
  hint?: ReactNode;
  optional?: boolean;
  htmlFor?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <Label.Root htmlFor={htmlFor} className="label text-fg-muted">
          {label}
        </Label.Root>
        {optional ? <span className="text-2xs text-fg-faint">optional</span> : null}
      </div>
      {children}
      {hint ? <p className="text-xs leading-relaxed text-fg-faint">{hint}</p> : null}
    </div>
  );
}
