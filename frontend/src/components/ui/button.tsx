"use client";

import { Slot } from "radix-ui";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "outline" | "danger";
type Size = "sm" | "md" | "lg" | "icon";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  asChild?: boolean;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent text-accent-on hover:bg-accent-hi active:translate-y-px disabled:hover:bg-accent",
  secondary:
    "bg-surface text-fg border border-line hover:bg-surface-2 hover:border-line-strong",
  outline:
    "bg-transparent text-fg border border-line-strong hover:bg-surface-2",
  ghost: "bg-transparent text-fg-muted hover:bg-surface-2 hover:text-fg",
  danger: "bg-bad-soft text-bad border border-transparent hover:border-bad/40",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 gap-1.5 px-3 text-[13px]",
  md: "h-9 gap-2 px-3.5 text-sm",
  lg: "h-11 gap-2 px-5 text-[15px]",
  icon: "size-9 justify-center",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "secondary", size = "md", asChild, ...props },
  ref,
) {
  const Component = asChild ? Slot.Root : "button";
  return (
    <Component
      ref={ref}
      className={cn(
        "inline-flex select-none items-center rounded-ctl font-medium whitespace-nowrap",
        "transition-colors duration-150",
        "disabled:pointer-events-none disabled:opacity-45",
        "[&_svg]:size-4 [&_svg]:shrink-0",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    />
  );
});
