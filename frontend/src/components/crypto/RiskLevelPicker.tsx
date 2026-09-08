import { useEffect, useRef, useState } from "react";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { RiskLevel } from "@/types";

const RISK_LEVELS: RiskLevel[] = ["low", "medium", "high"];
// Traffic-light metaphor: green/yellow/red, not this app's usual gray-for-
// medium risk convention (see CryptoRiskAllocationBody) — picked for a
// picker that needs to read at a glance. --series-4 is the dataviz skill's
// validated yellow slot.
const RISK_COLOR: Record<RiskLevel, string> = {
  low: "var(--success)",
  medium: "var(--series-4)",
  high: "var(--danger)",
};
// How many of the 3 bars are filled for each level — low is "a little
// risk", not "no risk", so it still lights up one bar rather than none.
const FILLED_BARS: Record<RiskLevel, number> = { low: 1, medium: 2, high: 3 };
const BAR_HEIGHTS = ["h-1.5", "h-2.5", "h-3.5"];

/** Three ascending bars, signal-strength style — same shape Linear uses for
 * its Priority column. Filled bars are colored per `level`; the rest sit at
 * a flat muted height so the icon always reads as "N of 3", not just a
 * color. `size` scales the whole icon (picker trigger vs. menu options). */
function RiskBars({ level, size = 1 }: { level: RiskLevel; size?: number }) {
  const filled = FILLED_BARS[level];
  return (
    <span className="flex items-end gap-0.5" style={{ transform: `scale(${size})` }}>
      {BAR_HEIGHTS.map((height, index) => (
        <span
          key={index}
          className={`w-1 rounded-sm ${height}`}
          style={{ backgroundColor: index < filled ? RISK_COLOR[level] : "var(--border)" }}
        />
      ))}
    </span>
  );
}

interface RiskLevelPickerProps {
  value: RiskLevel;
  onChange: (level: RiskLevel) => void;
}

/** The Crypto holdings table's risk-level control: a signal-bar icon (1-3
 * bars lit, colored green/yellow/red) showing the current level — click it
 * to open a compact menu of all three and pick one. Encodes both color and
 * magnitude, so it reads at a glance without relying on color alone. */
export function RiskLevelPicker({ value, onChange }: RiskLevelPickerProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleOutsideClick(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [open]);

  return (
    <span ref={rootRef} className="relative inline-block">
      <button
        type="button"
        aria-label={t(`netWorth.riskLevel.${value}` as TranslationKey)}
        title={t(`netWorth.riskLevel.${value}` as TranslationKey)}
        onClick={() => setOpen((prev) => !prev)}
        className="flex items-center rounded p-1 hover:bg-surface-2"
      >
        <RiskBars level={value} />
      </button>
      {open && (
        <span className="absolute right-0 top-full z-10 mt-1 flex flex-col gap-0.5 rounded-lg border border-border bg-surface-1 p-1 shadow-md">
          {RISK_LEVELS.map((level) => (
            <button
              key={level}
              type="button"
              onClick={() => {
                onChange(level);
                setOpen(false);
              }}
              className={`flex items-center gap-2 whitespace-nowrap rounded-md px-2 py-1.5 text-left text-xs ${
                level === value ? "bg-surface-2 font-medium text-text-primary" : "text-text-secondary hover:bg-surface-2"
              }`}
            >
              <RiskBars level={level} />
              {t(`netWorth.riskLevel.${level}` as TranslationKey)}
            </button>
          ))}
        </span>
      )}
    </span>
  );
}
