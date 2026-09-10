import { type ReactNode, useEffect, useState } from "react";
import { Logo } from "@/components/layout/Logo";
import { LoginScreen } from "@/components/auth/LoginScreen";
import { NoAuthModal } from "@/components/auth/NoAuthModal";
import { checkCredentials, useAuthHeader, whenAuthRestored } from "@/lib/auth";

// "not-configured" and "authenticated" both render `children` the same way,
// but they must stay distinct: only "not-configured" means this instance has
// no AURUM_BASIC_AUTH_USER/PASSWORD at all (nginx never sent 401 to our
// deliberately-wrong probe header), which is what triggers NoAuthModal.
// Collapsing them back into one "not-required" state would make an
// authenticated session with valid stored credentials show the "this
// instance has no password" warning too.
type Probe = "checking" | "required" | "not-configured" | "authenticated";

/** Wraps the whole app. Renders the login screen only when this instance
 * actually has Basic Auth turned on (AURUM_BASIC_AUTH_USER/PASSWORD in
 * .env, see frontend/docker-entrypoint.d/20-basic-auth.sh) — most installs
 * don't, and this must never force a login screen on those. When stored
 * credentials go stale (password changed, or auth was just turned on) the
 * 401 handler in api/client.ts clears them, useAuthHeader() picks that up
 * reactively, and this falls back to the login screen on its own. */
export function LoginGate({ children }: { children: ReactNode }) {
  const authHeader = useAuthHeader();
  const [probe, setProbe] = useState<Probe>(authHeader ? "authenticated" : "checking");

  useEffect(() => {
    if (authHeader) {
      setProbe("authenticated");
      return;
    }
    let cancelled = false;
    // Wait for the encrypted "remember me" credential to be read back before
    // concluding anything: it arrives asynchronously (IndexedDB + WebCrypto),
    // and probing first would show the login screen for a moment to someone
    // who is, in fact, already logged in. When it does arrive it sets the
    // header, which re-runs this effect down the authenticated path above.
    void whenAuthRestored()
      .then(() => (cancelled ? null : checkCredentials(null)))
      .then((result) => {
        if (cancelled || result === null) return;
        // A network/backend error here isn't an auth problem — don't block
        // the user behind a login screen for an unrelated outage, let the
        // app's own per-page error states (e.g. dashboard.errorLoading) explain it.
        setProbe(result === "unauthorized" ? "required" : "not-configured");
      });
    return () => {
      cancelled = true;
    };
  }, [authHeader]);

  if (probe === "checking") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-0">
        <Logo size={40} className="animate-pulse" />
      </div>
    );
  }

  if (probe === "required" && !authHeader) {
    return <LoginScreen />;
  }

  return (
    <>
      {probe === "not-configured" && <NoAuthModal />}
      {children}
    </>
  );
}
