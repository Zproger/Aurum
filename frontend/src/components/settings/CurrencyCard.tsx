import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useTranslation } from "@/lib/i18n";

export function CurrencyCard() {
  const { t, language } = useTranslation();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.currency")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-sm text-text-primary">USD — {language === "ru" ? "Доллар США" : "US Dollar"}</p>
        <p className="text-xs text-text-muted">{language === "ru" ? "Сводки и отчёты отображаются в USD. Валюта операции выбирается при её создании." : "Summaries and reports use USD. Select the transaction currency when creating a transaction."}</p>
      </CardContent>
    </Card>
  );
}
