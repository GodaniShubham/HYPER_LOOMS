import { AppShell } from "@/components/layout/app-shell";
import { Skeleton } from "@/components/ui/skeleton";

export default function JobResultLoading(): JSX.Element {
  return (
    <AppShell>
      <div className="space-y-4">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-[420px] w-full" />
      </div>
    </AppShell>
  );
}

