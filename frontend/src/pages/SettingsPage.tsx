import { AlertThresholdsCard } from "@/components/settings/AlertThresholdsCard";
import { BackupCard } from "@/components/settings/BackupCard";
import { CurrencyCard } from "@/components/settings/CurrencyCard";
import { PreferencesCard } from "@/components/settings/PreferencesCard";
import { useAppSettings } from "@/hooks/useSettings";
import { t } from "@/lib/i18n";

export function SettingsPage() {
  // Purely informational — if the settings request hasn't answered yet (or is
  // unreachable), just show nothing rather than a loading/error state for
  // one line of fine print.
  const { data: appSettings } = useAppSettings();

  return (
    <div className="space-y-5">
      <PreferencesCard />
      <CurrencyCard />
      <AlertThresholdsCard />
      <BackupCard />
      {appSettings?.app_version && (
        <p className="text-center text-xs text-text-muted">
          {t("settings.version", { version: appSettings.app_version })}
        </p>
      )}
    </div>
  );
}
