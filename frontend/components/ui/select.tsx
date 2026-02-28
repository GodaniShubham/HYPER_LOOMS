"use client";

import { SelectHTMLAttributes } from "react";

import { cn } from "@/hooks/use-classnames";

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>): JSX.Element {
  return (
    <select
      className={cn(
        "w-full rounded-xl border border-border/85 bg-background/55 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/80 focus:ring-2 focus:ring-primary/25",
        className
      )}
      {...props}
    />
  );
}
