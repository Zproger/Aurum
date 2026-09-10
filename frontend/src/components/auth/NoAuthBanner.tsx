import { useState } from "react";
import { TriangleAlert, X } from "lucide-react";
import { useTranslation } from "@/lib/i18n";

const DISMISS_KEY = "aurum:noAuthBanner:dismissed";

/** Shown by LoginGate for the entire session whenever this instance has no
 * AURUM_BASIC_AUTH_USER/PASSWORD configured (see frontend/docker-entrypoint.d/
 * 20-basic-auth.sh) — that state is otherwise only logged to the container's
 * stderr at startup, which most self-hosters never look at. Dismissal is
 * remembered only in sessionStorage, not localStorage, so the warning comes
 * back on the next visit instead of being silence-able forever. */
export function NoAuthBanner() {
  const { t } = useTranslation();
  const [dismissed, setDismissed] = useState(() => {
    try {
      return sessionStorage.getItem(DISMISS_KEY) === "1";
    } catch {
      return false;
    }
  });

  if (dismissed) return null;

  function handleDismiss() {
    setDismissed(true);
    try {
      sessionStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // storage unavailable — banner just reappears on next render, harmless
    }
  }

  return (
    <div className="flex items-start gap-2.5 border-b border-danger/30 bg-danger/10 px-4 py-2.5 text-sm text-danger">
      <TriangleAlert size={16} className="mt-0.5 shrink-0" />
      <span className="flex-1">{t("auth.noAuthBanner")}</span>
      <button
        type="button"
        onClick={handleDismiss}
        aria-label={t("auth.noAuthBannerDismiss")}
        className="shrink-0 rounded p-0.5 hover:bg-danger/20"
      >
        <X size={16} />
      </button>
    </div>
  );
}
