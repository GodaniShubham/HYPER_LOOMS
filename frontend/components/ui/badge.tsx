import { HTMLAttributes } from "react";

import { cn } from "@/hooks/use-classnames";

type BadgeTone = "neutral" | "success" | "warning" | "danger";

const toneMap: Record<BadgeTone, string> = {
  neutral: "bg-white/5 text-muted-foreground border border-border/90",
  success: "bg-success/20 text-success border border-success/60",
  warning: "bg-warning/20 text-warning border border-warning/60",
  danger: "bg-danger/15 text-danger border border-danger/60",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

export function Badge({ className, tone = "neutral", ...props }: BadgeProps): JSX.Element {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-medium tracking-[0.04em]",
        toneMap[tone],
        className
      )}
      {...props}
    />
  );
}
