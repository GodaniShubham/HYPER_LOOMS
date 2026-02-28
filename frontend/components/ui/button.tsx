"use client";

import { ButtonHTMLAttributes, forwardRef } from "react";

import { cn } from "@/hooks/use-classnames";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const variantMap: Record<ButtonVariant, string> = {
  primary:
    "bg-gradient-to-r from-primary to-accent text-primary-foreground border border-primary/70 shadow-glow hover:brightness-110",
  secondary:
    "bg-card/85 text-foreground border border-border/80 shadow-panel hover:border-primary/45 hover:bg-card",
  ghost:
    "bg-transparent text-muted-foreground border border-transparent hover:text-foreground hover:bg-white/5 hover:border-border/80",
  danger: "bg-danger/90 text-white border border-danger/60 shadow-panel hover:brightness-110",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "primary", ...props },
  ref
) {
  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition duration-200 disabled:cursor-not-allowed disabled:opacity-50",
        variantMap[variant],
        className
      )}
      {...props}
    />
  );
});
