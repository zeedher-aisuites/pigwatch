import type { ReactNode } from "react";

type Tone = "positive" | "negative" | "warning" | "neutral" | "accent";

export function StatusBadge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`status-badge status-badge--${tone}`}>{children}</span>;
}
