"use client";

import { Check, ChevronDown, Minus } from "lucide-react";
import { Checkbox, Select, Separator, Slider, Switch, Tabs, Tooltip } from "radix-ui";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------- checkbox */

export function CheckboxField({
  checked,
  onCheckedChange,
  label,
  hint,
  className,
  indeterminate,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
  className?: string;
  indeterminate?: boolean;
}) {
  return (
    <label
      className={cn(
        "group flex cursor-pointer items-start gap-3 rounded-ctl border border-transparent px-2 py-1.5",
        "transition-colors hover:bg-surface-2",
        className,
      )}
    >
      <Checkbox.Root
        checked={indeterminate ? "indeterminate" : checked}
        onCheckedChange={(value) => onCheckedChange(value === true)}
        className={cn(
          "mt-0.5 grid size-4.5 shrink-0 place-items-center rounded-[5px] border transition-colors",
          "border-line-strong bg-surface",
          "data-[state=checked]:border-accent data-[state=checked]:bg-accent",
          "data-[state=indeterminate]:border-accent data-[state=indeterminate]:bg-accent",
        )}
      >
        <Checkbox.Indicator className="text-accent-on">
          {indeterminate ? <Minus className="size-3" /> : <Check className="size-3" strokeWidth={3} />}
        </Checkbox.Indicator>
      </Checkbox.Root>
      <span className="min-w-0">
        <span className="block text-sm leading-tight">{label}</span>
        {hint ? <span className="mt-0.5 block text-xs text-fg-faint">{hint}</span> : null}
      </span>
    </label>
  );
}

/* ---------------------------------------------------------------- switch */

export function SwitchField({
  checked,
  onCheckedChange,
  label,
  hint,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-4 py-1.5">
      <span className="min-w-0">
        <span className="block text-sm">{label}</span>
        {hint ? <span className="mt-0.5 block text-xs text-fg-faint">{hint}</span> : null}
      </span>
      <Switch.Root
        checked={checked}
        onCheckedChange={onCheckedChange}
        className={cn(
          "relative h-5 w-9 shrink-0 rounded-pill border border-line-strong bg-surface-3 transition-colors",
          "data-[state=checked]:border-accent data-[state=checked]:bg-accent",
        )}
      >
        <Switch.Thumb className="block size-3.5 translate-x-[3px] rounded-full bg-fg-muted transition-transform data-[state=checked]:translate-x-[19px] data-[state=checked]:bg-accent-on" />
      </Switch.Root>
    </label>
  );
}

/* ---------------------------------------------------------------- select */

export function SelectField({
  value,
  onValueChange,
  options,
  placeholder = "Select…",
  className,
  ariaLabel,
}: {
  value?: string;
  onValueChange: (value: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <Select.Root value={value} onValueChange={onValueChange}>
      <Select.Trigger
        aria-label={ariaLabel}
        className={cn(
          "inline-flex h-9 items-center justify-between gap-2 rounded-ctl border border-line bg-surface px-3 text-sm",
          "transition-colors hover:border-line-strong data-[placeholder]:text-fg-faint",
          className,
        )}
      >
        <Select.Value placeholder={placeholder} />
        <Select.Icon>
          <ChevronDown className="size-3.5 text-fg-faint" />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          position="popper"
          sideOffset={6}
          className="z-50 max-h-72 min-w-(--radix-select-trigger-width) overflow-hidden rounded-card border border-line bg-surface shadow-pop"
        >
          <Select.Viewport className="p-1">
            {options.map((option) => (
              <Select.Item
                key={option.value}
                value={option.value}
                className={cn(
                  "flex cursor-pointer items-center justify-between gap-3 rounded-[7px] px-2.5 py-1.5 text-sm outline-none",
                  "data-[highlighted]:bg-surface-2 data-[state=checked]:text-accent",
                )}
              >
                <Select.ItemText>{option.label}</Select.ItemText>
                <Select.ItemIndicator>
                  <Check className="size-3.5" />
                </Select.ItemIndicator>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}

/* ---------------------------------------------------------------- slider */

export function WeightSlider({
  value,
  onValueChange,
  max = 40,
  ariaLabel,
}: {
  value: number;
  onValueChange: (value: number) => void;
  max?: number;
  ariaLabel: string;
}) {
  return (
    <Slider.Root
      value={[value]}
      min={0}
      max={max}
      step={1}
      onValueChange={([next]) => onValueChange(next)}
      className="relative flex h-5 w-full touch-none items-center select-none"
      aria-label={ariaLabel}
    >
      <Slider.Track className="relative h-1 w-full grow rounded-pill bg-surface-3">
        <Slider.Range className="absolute h-full rounded-pill bg-accent" />
      </Slider.Track>
      <Slider.Thumb className="block size-3.5 rounded-full border-2 border-accent bg-surface transition-transform hover:scale-110" />
    </Slider.Root>
  );
}

/* ------------------------------------------------------------------ tabs */

export function TabsRoot({
  value,
  onValueChange,
  tabs,
  children,
  className,
}: {
  value: string;
  onValueChange: (value: string) => void;
  tabs: { value: string; label: string; count?: number }[];
  children: ReactNode;
  className?: string;
}) {
  return (
    <Tabs.Root value={value} onValueChange={onValueChange} className={className}>
      <Tabs.List className="flex items-center gap-1 border-b border-line">
        {tabs.map((tab) => (
          <Tabs.Trigger
            key={tab.value}
            value={tab.value}
            className={cn(
              "-mb-px flex items-center gap-2 border-b-2 border-transparent px-3 py-2 text-sm text-fg-muted",
              "transition-colors hover:text-fg data-[state=active]:border-accent data-[state=active]:text-fg",
            )}
          >
            {tab.label}
            {tab.count != null ? (
              <span className="num rounded-pill bg-surface-2 px-1.5 text-2xs text-fg-muted">
                {tab.count}
              </span>
            ) : null}
          </Tabs.Trigger>
        ))}
      </Tabs.List>
      {children}
    </Tabs.Root>
  );
}

export const TabPanel = Tabs.Content;

/* --------------------------------------------------------------- tooltip */

export function Hint({ children, label }: { children: ReactNode; label: ReactNode }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          sideOffset={6}
          className="z-50 max-w-72 rounded-ctl border border-line bg-surface px-2.5 py-1.5 text-xs leading-relaxed text-fg shadow-pop"
        >
          {label}
          <Tooltip.Arrow className="fill-[var(--color-surface)]" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export const Divider = ({ className }: { className?: string }) => (
  <Separator.Root className={cn("hairline my-4", className)} />
);
