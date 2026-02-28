import { AppShell } from "@/components/layout/app-shell";
import { Skeleton } from "@/components/ui/skeleton";

export default function JobsLoading(): JSX.Element {
  return (
    <AppShell>
      <div className="grid gap-4 xl:grid-cols-[2fr,1fr]">
        <div className="space-y-4">
          <Skeleton className="h-72 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
        <Skeleton className="h-[540px] w-full" />
      </div>
    </AppShell>
  );
}

