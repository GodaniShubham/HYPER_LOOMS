"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ResultViewer } from "@/modules/jobs/components/result-viewer";
import { getJob } from "@/services/api/jobs";
import { useRuntimeState } from "@/hooks/use-runtime-state";

export default function JobResultPage(): JSX.Element {
  const runtime = useRuntimeState();
  const params = useParams<{ jobId: string }>();
  const jobId = params?.jobId;

  const jobQuery = useQuery({
    queryKey: ["job-result", jobId],
    queryFn: () => getJob(jobId!),
    enabled: runtime.isOnline && Boolean(jobId),
    refetchInterval: runtime.isInteractive ? 10000 : false,
  });

  return (
    <AppShell>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold text-foreground">Job Result</h1>
          <Link href="/jobs">
            <Button variant="secondary">Back to Console</Button>
          </Link>
        </div>

        {jobQuery.isLoading ? <Skeleton className="h-80 w-full" /> : null}
        {jobQuery.isError ? (
          <div className="rounded-2xl border border-danger/50 bg-danger/10 p-4 text-sm text-danger">
            Could not load job result.
          </div>
        ) : null}
        {jobQuery.data ? <ResultViewer job={jobQuery.data} /> : null}
      </div>
    </AppShell>
  );
}
