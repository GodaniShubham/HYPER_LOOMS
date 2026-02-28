"use client";

import { forwardRef, TextareaHTMLAttributes } from "react";

import { cn } from "@/hooks/use-classnames";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className, ...props },
  ref
) {
  return (
    <textarea
      ref={ref}
      className={cn(
        "min-h-[180px] w-full resize-y rounded-xl border border-border/85 bg-background/55 px-3 py-3 text-sm leading-6 text-foreground outline-none transition focus:border-primary/80 focus:ring-2 focus:ring-primary/25",
        className
      )}
      {...props}
    />
  );
});
