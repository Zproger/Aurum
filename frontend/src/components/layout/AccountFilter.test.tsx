import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { setLanguage } from "@/lib/i18n";

vi.hoisted(() => {
  Object.defineProperty(window, "matchMedia", { configurable: true, value: () => ({ matches: false, addEventListener() {} }) });
});

const accounts = [
  { id: 1, name: "Kaspi Gold", type: "debit_card", currency: "KZT", color: null, is_archived: false },
  { id: 2, name: "Cash", type: "cash", currency: "KZT", color: null, is_archived: false },
  { id: 3, name: "Old card", type: "debit_card", currency: "USD", color: null, is_archived: true },
];
vi.mock("@/hooks/useAccounts", () => ({ useAccounts: () => ({ data: accounts }) }));
vi.mock("@/contexts/WorkspaceContext", () => ({ useWorkspace: () => ({ activeWorkspace: { id: "ws-test" } }) }));

const { AccountFilter, AccountFilterNotice } = await import("./AccountFilter");
const { useAccountFilter } = await import("@/hooks/useAccountFilter");

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let root: Root | null = null;
let container: HTMLDivElement | null = null;
let seen: number[] | undefined | "unset" = "unset";

function Probe() {
  seen = useAccountFilter().accountIds;
  return null;
}

async function render() {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => { root?.render(<><AccountFilter /><AccountFilterNotice /><Probe /></>); });
  return container;
}

const button = (text: string) =>
  Array.from(document.querySelectorAll("button")).find((item) => item.textContent?.includes(text))!;
const box = (name: string) =>
  Array.from(document.querySelectorAll("label")).find((label) => label.textContent?.includes(name))!.querySelector("input")!;

beforeEach(() => { setLanguage("en"); localStorage.clear(); });
afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  document.body.innerHTML = "";
});

it("sends no filter until an account is excluded, then lists the included ones", async () => {
  await render();
  expect(seen).toBeUndefined();
  expect(button("All accounts")).toBeDefined();

  await act(async () => { button("All accounts").click(); });
  await act(async () => { box("Cash").click(); });

  expect(seen).toEqual([1, 3]);
  expect(button("Accounts: 2 of 3")).toBeDefined();
  expect(document.body.textContent).toContain("Totals exclude these accounts: Cash.");
  // Remembered per workspace in this browser.
  expect(JSON.parse(localStorage.getItem("aurum:account-filter:ws-test")!)).toEqual([2]);
});

it("keeps at least one account selected and can reset to all", async () => {
  await render();
  await act(async () => { button("All accounts").click(); });
  const onlyButtons = Array.from(document.querySelectorAll("button")).filter((item) => item.textContent === "Only this");
  await act(async () => { onlyButtons[0].click(); });

  expect(seen).toEqual([1]);
  expect(box("Kaspi Gold").disabled).toBe(true);

  await act(async () => { button("Select all").click(); });
  expect(seen).toBeUndefined();
});
