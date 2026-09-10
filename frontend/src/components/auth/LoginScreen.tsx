import { type FormEvent, useState } from "react";
import { Logo } from "@/components/layout/Logo";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { buildBasicAuthHeader, checkCredentials, isRememberSupported, setCredentials } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";

type Status = "idle" | "submitting" | "invalid" | "unreachable";

/** Shown by LoginGate when this instance requires Basic Auth and no valid
 * credentials are stored yet. Doesn't implement auth itself — it just
 * collects a username/password, checks them against a real protected
 * endpoint, and on success hands them to lib/auth.ts's setCredentials(),
 * which is what every subsequent request actually authenticates with. */
export function LoginScreen() {
  const { t } = useTranslation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  // Remembering encrypts the credential with WebCrypto, which browsers only
  // expose in a secure context — over plain HTTP to a LAN address there's no
  // safe way to persist it, so the option is hidden rather than offered and
  // quietly ignored. See lib/credentialVault.ts.
  const canRemember = isRememberSupported();

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setStatus("submitting");
    const result = await checkCredentials(buildBasicAuthHeader(username, password));
    if (result === "ok") {
      setCredentials(username, password, canRemember && remember);
      return;
    }
    setStatus(result === "unauthorized" ? "invalid" : "unreachable");
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 px-4">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col items-center gap-6 p-6 pt-8 sm:p-8">
          <div className="flex flex-col items-center gap-1.5">
            <Logo size={40} />
            <span className="text-lg font-semibold tracking-tight text-text-primary">Aurum</span>
            <span className="text-xs text-text-muted">{t("auth.subtitle")}</span>
          </div>

          <form onSubmit={handleSubmit} className="flex w-full flex-col gap-4">
            <div>
              <Label htmlFor="auth-username">{t("auth.usernameLabel")}</Label>
              <Input
                id="auth-username"
                name="username"
                autoComplete="username"
                autoFocus
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="auth-password">{t("auth.passwordLabel")}</Label>
              <Input
                id="auth-password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>

            {canRemember ? (
              <label className="flex items-center gap-2 text-xs text-text-muted">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(event) => setRemember(event.target.checked)}
                  className="h-3.5 w-3.5 accent-text-primary"
                />
                {t("auth.rememberMe")}
              </label>
            ) : (
              <p className="text-xs text-text-muted">{t("auth.sessionOnlyHint")}</p>
            )}

            {status === "invalid" && <p className="text-sm text-danger">{t("auth.errorInvalidCredentials")}</p>}
            {status === "unreachable" && <p className="text-sm text-danger">{t("auth.errorUnreachable")}</p>}

            <Button type="submit" className="w-full" disabled={status === "submitting"}>
              {status === "submitting" ? t("auth.submitting") : t("auth.submitButton")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
