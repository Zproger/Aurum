import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";
import { useAppSettings } from "@/hooks/useSettings";
import { setCurrency } from "@/lib/i18n";
import { AccountsPage } from "@/pages/AccountsPage";
import { AdvicePage } from "@/pages/AdvicePage";
import { BudgetPage } from "@/pages/BudgetPage";
import { CashFlowPage } from "@/pages/CashFlowPage";
import { CategoriesPage } from "@/pages/CategoriesPage";
import { CryptoPage } from "@/pages/CryptoPage";
import { CsvImportPage } from "@/pages/CsvImportPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { GoalsPage } from "@/pages/GoalsPage";
import { NetWorthPage } from "@/pages/NetWorthPage";
import { RecurringPage } from "@/pages/RecurringPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { RoiPage } from "@/pages/RoiPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { TransactionsPage } from "@/pages/TransactionsPage";

export default function App() {
  const [collapsed, setCollapsed] = useLocalStorageState("aurum:sidebar-collapsed", false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // Primary currency is server-persisted, unlike language — sync the
  // client-side reactive mirror (lib/i18n's getCurrency/formatCurrency)
  // once the setting loads, so it's not stuck on the "USD" fallback default.
  const { data: settings } = useAppSettings();
  useEffect(() => {
    if (settings) setCurrency(settings.currency);
  }, [settings]);

  return (
    <div className="flex min-h-screen bg-surface-0">
      <Sidebar
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed(!collapsed)}
        mobileOpen={mobileNavOpen}
        onCloseMobile={() => setMobileNavOpen(false)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onOpenMobileNav={() => setMobileNavOpen(true)} />
        {/* No max-width cap — the sidebar can be collapsed to free up space
            (see Sidebar.tsx's collapsed w-[72px] vs expanded w-56), and a
            fixed max-w here would leave that freed space as dead centered
            gutter instead of handing it to the page. Padding alone keeps
            content off the sidebar/viewport edges. */}
        <main className="w-full px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/net-worth" element={<NetWorthPage />} />
            <Route path="/crypto" element={<CryptoPage />} />
            <Route path="/roi" element={<RoiPage />} />
            <Route path="/accounts" element={<AccountsPage />} />
            <Route path="/categories" element={<CategoriesPage />} />
            <Route path="/cash-flow" element={<CashFlowPage />} />
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/transactions/import" element={<CsvImportPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/budget" element={<BudgetPage />} />
            <Route path="/advice" element={<AdvicePage />} />
            <Route path="/goals" element={<GoalsPage />} />
            <Route path="/recurring" element={<RecurringPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
