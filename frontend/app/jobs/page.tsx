import { AppShell } from "@/components/layout/app-shell";
import { JobConsole } from "@/modules/jobs/components/job-console";

export default function JobsPage(): JSX.Element {
  return (
    <AppShell>
      <JobConsole />
    </AppShell>
  );
}

