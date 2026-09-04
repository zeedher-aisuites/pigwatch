import type { SourceDelivery, SourceOrigin } from "../api/types";
import { StatusBadge } from "./StatusBadge";

export function Provenance({
  origin,
  delivery,
  compact = false,
}: {
  origin: SourceOrigin;
  delivery: SourceDelivery;
  compact?: boolean;
}) {
  return (
    <span className={`provenance ${compact ? "provenance--compact" : ""}`}>
      <span className="provenance__dimension">
        {!compact && <span className="provenance__label">Origin</span>}
        <StatusBadge tone={origin === "SYNTHETIC" ? "accent" : "neutral"}>{origin}</StatusBadge>
      </span>
      <span className="provenance__dimension">
        {!compact && <span className="provenance__label">Delivery</span>}
        <StatusBadge tone={delivery === "LIVE" ? "positive" : "warning"}>{delivery}</StatusBadge>
      </span>
    </span>
  );
}
