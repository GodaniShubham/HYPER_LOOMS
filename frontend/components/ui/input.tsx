"use client";

import { forwardRef, InputHTMLAttributes } from "react";

import { cn } from "@/hooks/use-classnames";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...props },
  ref
) {
  return (
    <input
      ref={ref}
      className={cn(
        "w-full rounded-xl border border-border/85 bg-background/55 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/80 focus:ring-2 focus:ring-primary/25",
        className
      )}
      {...props}
    />
  );
});
