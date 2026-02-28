import { HTMLAttributes } from "react";

import { cn } from "@/hooks/use-classnames";

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>): JSX.Element {
  return <div className={cn("animate-pulse rounded-md bg-white/10", className)} {...props} />;
}

