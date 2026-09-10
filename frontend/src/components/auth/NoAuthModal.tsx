import { useState } from "react";
import { ShieldAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n";

const ACK_KEY = "aurum:noAuthAcknowledged";

/** Shown by LoginGate once (ever, per browser) when this instance has no
 * AURUM_BASIC_AUTH_USER/PASSWORD configured (see frontend/docker-entrypoint.d/
 * 20-basic-auth.sh) — that state is otherwise only logged to the container's
 * stderr at startup, which most self-hosters never look at. Unlike a normal
 * Dialog, there is deliberately no backdrop-click, Escape, or X-button way
 * out — the only way past it is the explicit "I understand the risk" button,
 * whose click is what persists the acknowledgement. */
export function NoAuthModal() {
  const { t } = useTranslation();
  const [acknowledged, setAcknowledged] = useState(() => {
    try {
      return localStorage.getItem(ACK_KEY) === "1";
    } catch {
      return false;
    }
  });

  if (acknowledged) return null;

  function handleAccept() {
    setAcknowledged(true);
    try {
      localStorage.setItem(ACK_KEY, "1");
    } catch {
      // storage unavailable — modal just reappears next reload, harmless
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-sm rounded-2xl border border-danger/30 bg-surface-1 p-6 text-center shadow-xl">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-danger/10 text-danger">
          <ShieldAlert size={24} />
        </div>
        <h2 className="mb-2 text-base font-semibold text-text-primary">{t("auth.noAuthModalTitle")}</h2>
        <p className="mb-6 text-sm text-text-secondary">{t("auth.noAuthModalBody")}</p>
        <button
          type="button"
          onClick={handleAccept}
          className="inline-flex h-10 w-full items-center justify-center rounded-lg bg-danger px-4 text-sm font-medium text-white transition-colors hover:opacity-90"
        >
          {t("auth.noAuthModalAccept")}
        </button>
      </div>
    </div>
  );
}
