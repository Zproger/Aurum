import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { formatCurrency } from "@/lib/format";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { RiskLevelSummary } from "@/types";

interface RiskAllocationCardProps {
  riskLevels: RiskLevelSummary[];
  isLoading: boolean;
}

export function RiskAllocationCard({ riskLevels, isLoading }: RiskAllocationCardProps) {
  const { t } = useTranslation();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("netWorth.riskAllocationTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {riskLevels.map((tier) => (
              <div key={tier.risk_level} className="rounded-lg border border-border p-3.5">
                <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: tier.color }} />
                  {t(`netWorth.riskLevel.${tier.risk_level}` as TranslationKey)}
                </p>
                <p className="mt-1.5 text-xl font-semibold tabular-nums text-text-primary">
                  {formatCurrency(tier.total_value)}
                </p>
                <p className="mt-1 text-xs text-text-muted">{tier.percent.toFixed(1)}% {t("netWorth.riskAllocationOfCapital")}</p>

                {tier.items.length > 0 && (
                  <ul className="mt-3 space-y-1.5 border-t border-gridline pt-3">
                    {tier.items.map((item) => (
                      <li key={item.key} className="flex items-center gap-2">
                        <span className="min-w-0 flex-1 truncate text-xs text-text-secondary">
                          {item.key === "cash" ? t("netWorth.assetClass.cash") : item.name}
                        </span>
                        <span className="h-1 w-10 shrink-0 overflow-hidden rounded-full bg-surface-2">
                          <span
                            className="block h-full rounded-full"
                            style={{ width: `${item.percent}%`, backgroundColor: tier.color }}
                          />
                        </span>
                        <span className="w-8 shrink-0 text-right text-[11px] tabular-nums text-text-muted">
                          {item.percent.toFixed(1)}%
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
