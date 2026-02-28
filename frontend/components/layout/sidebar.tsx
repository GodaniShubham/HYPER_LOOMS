"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, LayoutDashboard, ServerCog, Sparkles, Gauge } from "lucide-react";

import { cn } from "@/hooks/use-classnames";

const navItems = [
  { href: "/", label: "Command Deck", icon: LayoutDashboard },
  { href: "/jobs", label: "Training Studio", icon: Sparkles },
  { href: "/admin", label: "Operations", icon: ServerCog },
];

export function Sidebar(): JSX.Element {
  const pathname = usePathname();

  return (
    <aside className="w-full rounded-2xl border border-border/80 bg-card/68 p-4 backdrop-blur-md shadow-panel lg:w-[270px]">
      <div className="metal-panel mb-6 rounded-xl p-3">
        <div className="mb-2 flex items-center gap-2">
          <Activity className="h-4 w-4 text-primary animate-ember" />
          <p className="section-kicker">Hyperlooms</p>
        </div>
        <div>
          <p className="text-sm font-semibold text-foreground">Distributed Model Exchange</p>
          <p className="text-xs text-muted-foreground">Training + inference orchestration</p>
        </div>
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 px-2.5 py-1.5 text-xs text-primary">
          <Gauge className="h-3.5 w-3.5 animate-blink-trace" />
          <span>Fabric Sync Enabled</span>
        </div>
      </div>

      <nav className="space-y-1.5">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2 rounded-xl px-3 py-2 text-sm transition",
                active
                  ? "bg-primary/18 text-primary border border-primary/45 shadow-glow"
                  : "text-muted-foreground hover:bg-white/5 hover:text-foreground hover:border hover:border-border/80"
              )}
            >
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
