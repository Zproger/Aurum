import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { formatCryptoAmount, maskAmount } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { CryptoHolding } from "@/types";

interface CryptoAllocationBodyProps {
  holdings: CryptoHolding[];
  isLoading: boolean;
  hidden: boolean;
}

// Fixed categorical order, same 8-slot ramp the rest of the app already
// validated (see net_worth_service.py's _CLASS_META comment) — a coin never
// gets a freshly generated hue. Only the first 7 get their own color; an 8th+
// coin folds into "Other" (--series-other) rather than cycling back through
// the ramp, per the dataviz skill's categorical-color rule.
const SERIES_COLORS = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
  "var(--series-6)",
  "var(--series-7)",
];
const OTHER_COLOR = "var(--series-other)";
const MAX_SLICES = SERIES_COLORS.length;

export interface Slice {
  key: string;
  name: string;
  symbol: string | null;
  amount: number;
  color: string;
}

// Exported for direct unit testing (see CryptoAllocationBody.test.ts) —
// the donut/table JSX below isn't worth rendering just to check the math.
export function buildSlices(holdings: CryptoHolding[]): Slice[] {
  const priced = holdings
    .filter((h) => h.value !== null && Number(h.value) > 0)
    .map((h) => ({ key: String(h.asset_id), name: h.name, symbol: h.symbol, amount: Number(h.value) }))
    .sort((a, b) => b.amount - a.amount);

  const top = priced.slice(0, MAX_SLICES).map((item, index) => ({ ...item, color: SERIES_COLORS[index] }));
  const rest = priced.slice(MAX_SLICES);
  if (rest.length === 0) return top;

  const otherTotal = rest.reduce((sum, item) => sum + item.amount, 0);
  return [...top, { key: "other", name: "Other", symbol: null, amount: otherTotal, color: OTHER_COLOR }];
}

function DonutTooltip({
  active,
  payload,
  hidden,
  otherLabel,
}: {
  active?: boolean;
  payload?: Array<{ payload: Slice & { percent: number } }>;
  hidden: boolean;
  otherLabel: string;
}) {
  if (!active || !payload?.length) return null;
  const slice = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-surface-1 px-3 py-2 text-sm shadow-md">
      <p className="font-medium text-text-primary">{slice.key === "other" ? otherLabel : slice.name}</p>
      <p className="text-text-muted">
        {maskAmount(formatCryptoAmount(slice.amount), hidden)} · {slice.percent.toFixed(1)}%
      </p>
    </div>
  );
}

/** The "Allocation" tab's content inside CryptoOverviewCard — a donut
 * (part-to-whole across few categories is exactly the case a donut is fine
 * for) plus a compact table: a color swatch identifying the ticker, its
 * share, and the amount. A real <table>, not a flex row list — table
 * columns size to their own content and align natively, so this can't
 * stretch across whatever space is left next to the donut the way a
 * flex-1 row did. */
export function CryptoAllocationBody({ holdings, isLoading, hidden }: CryptoAllocationBodyProps) {
  const { t } = useTranslation();

  if (isLoading) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>;
  }
  const slices = buildSlices(holdings);
  if (slices.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("crypto.empty")}</p>;
  }

  const total = slices.reduce((sum, slice) => sum + slice.amount, 0);
  const donutData = slices.map((slice) => ({ ...slice, percent: (slice.amount / total) * 100 }));

  return (
    <div className="flex flex-col items-center justify-center gap-6 sm:flex-row">
      <div className="h-48 w-48 shrink-0 sm:h-56 sm:w-56">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={donutData}
              dataKey="amount"
              nameKey="name"
              innerRadius="68%"
              outerRadius="100%"
              paddingAngle={donutData.length > 1 ? 2 : 0}
              stroke="var(--surface-1)"
              strokeWidth={2}
              isAnimationActive={false}
            >
              {donutData.map((slice) => (
                <Cell key={slice.key} fill={slice.color} />
              ))}
            </Pie>
            <Tooltip content={<DonutTooltip hidden={hidden} otherLabel={t("crypto.allocation.other")} />} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <table className="text-sm">
        <tbody>
          {donutData.map((slice) => (
            <tr key={slice.key} title={slice.key === "other" ? undefined : slice.name}>
              <td className="py-1.5 pr-3">
                <span className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: slice.color }} />
                  <span className="font-medium text-text-primary">
                    {slice.key === "other" ? t("crypto.allocation.other") : slice.symbol}
                  </span>
                </span>
              </td>
              <td className="py-1.5 pr-3 text-right font-medium tabular-nums text-text-primary">
                {slice.percent.toFixed(1)}%
              </td>
              <td className="py-1.5 text-right tabular-nums text-text-muted">{maskAmount(formatCryptoAmount(slice.amount), hidden)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
