import { HTMLAttributes } from "react";

import { cn } from "@/hooks/use-classnames";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>): JSX.Element {
  return (
    <div
      className={cn(
        "animate-rise-fade rounded-2xl border border-border/85 bg-card/88 p-5 backdrop-blur-sm shadow-panel",
        className
      )}
      {...props}
    />
  );
}
