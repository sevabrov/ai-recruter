import { Globe, Rss } from "lucide-react";
import type { ComponentType, ReactNode, SVGProps } from "react";
import type { Platform } from "@/services/types";
import { cn } from "@/lib/utils";

type IconProps = SVGProps<SVGSVGElement>;

/**
 * Platform glyphs are drawn here rather than imported: lucide dropped its brand
 * icons, and these stay legible at 14px in both themes.
 */
function InstagramGlyph(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
      <rect x="3" y="3" width="18" height="18" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.2" cy="6.8" r="1.1" fill="currentColor" stroke="none" />
    </svg>
  );
}

function LinkedinGlyph(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" {...props}>
      <path d="M4.5 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4ZM2.8 8.7h3.4V21H2.8V8.7Zm6 0h3.3v1.7c.6-1 1.8-2 3.6-2 2.6 0 4.3 1.7 4.3 5V21h-3.4v-6.9c0-1.6-.6-2.6-2-2.6-1.2 0-2 .8-2.3 1.7-.1.3-.1.7-.1 1.1V21H8.8s.05-11 0-12.3Z" />
    </svg>
  );
}

function FacebookGlyph(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" {...props}>
      <path d="M13.5 21v-7.5h2.6l.4-3h-3V8.6c0-.9.3-1.5 1.6-1.5h1.5V4.4c-.3 0-1.3-.1-2.4-.1-2.4 0-4.1 1.5-4.1 4.2v2H7.5v3h2.6V21h3.4Z" />
    </svg>
  );
}

function ThreadsGlyph(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
      <path
        d="M12 21c-4.6 0-7.4-3.2-7.4-9S7.5 3 12.1 3c3.3 0 5.5 1.5 6.4 4"
        strokeLinecap="round"
      />
      <path
        d="M8.9 14.4c0 1.6 1.4 2.6 3.2 2.6 2.2 0 3.6-1.3 3.6-3.6 0-2-1.5-3.3-4-3.3-2.9 0-4 1.2-4 1.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

const PLATFORM_ICONS: Record<Platform, ComponentType<IconProps>> = {
  instagram: InstagramGlyph,
  linkedin: LinkedinGlyph,
  facebook: FacebookGlyph,
  threads: ThreadsGlyph,
  website: Globe,
  blog: Rss,
};

export function PlatformIcon({
  platform,
  className,
}: {
  platform: Platform;
  className?: string;
}) {
  const Icon = PLATFORM_ICONS[platform];
  return <Icon className={cn("size-3.5", className)} aria-hidden />;
}

export function EmptyState({
  title,
  body,
  action,
  icon,
}: {
  title: string;
  body?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
      {icon ? (
        <div className="grid size-10 place-items-center rounded-full border border-line bg-surface-2 text-fg-faint">
          {icon}
        </div>
      ) : null}
      <h3 className="text-sm font-semibold">{title}</h3>
      {body ? <p className="max-w-sm text-sm text-fg-muted">{body}</p> : null}
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-ctl bg-surface-2",
        "after:absolute after:inset-0 after:w-1/3 after:bg-linear-to-r after:from-transparent after:via-surface-3 after:to-transparent",
        "after:content-[''] after:[animation:air-sweep_1.4s_ease-in-out_infinite]",
        className,
      )}
    />
  );
}

/** Mono uppercase caption used for section eyebrows and data labels. */
export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("label text-fg-faint", className)}>{children}</p>;
}

export function ConfidenceMeter({ value }: { value: number }) {
  const percent = Math.round(value * 100);
  return (
    <span className="inline-flex items-center gap-2" title={`Confidence ${percent}%`}>
      <span className="flex items-center gap-0.5" aria-hidden>
        {[0, 1, 2, 3, 4].map((index) => (
          <span
            key={index}
            className={cn(
              "block h-2.5 w-1 rounded-[1px]",
              percent >= (index + 1) * 20 ? "bg-accent" : "bg-surface-3",
            )}
          />
        ))}
      </span>
      <span className="num text-2xs text-fg-faint">{percent}%</span>
    </span>
  );
}
