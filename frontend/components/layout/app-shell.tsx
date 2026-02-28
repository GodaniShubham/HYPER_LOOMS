"use client";

import { PropsWithChildren } from "react";

import { Sidebar } from "@/components/layout/sidebar";

export function AppShell({ children }: PropsWithChildren): JSX.Element {
  return (
    <div className="mx-auto flex w-full max-w-[1480px] flex-col gap-4 px-4 pb-10 pt-5 lg:flex-row lg:px-7">
      <Sidebar />
      <main className="min-w-0 flex-1">
        <div className="rounded-2xl border border-border/75 bg-slate-950/28 p-3 shadow-panel sm:p-4 md:p-5">{children}</div>
      </main>
    </div>
  );
}
