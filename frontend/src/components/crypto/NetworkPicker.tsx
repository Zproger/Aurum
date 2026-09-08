import { useId, useState } from "react";
import { useTranslation } from "@/lib/i18n";

interface NetworkPickerProps {
  value: string | null;
  knownNetworks: string[];
  onChange: (network: string | null) => void;
}

/** Click-to-edit-in-place text for a holding's network (see
 * CryptoHolding.network) — a plain button that swaps for a text input on
 * click, autocompleting from every network already typed elsewhere via
 * `knownNetworks`. No fixed list: chains are numerous and change too often
 * for an enum, so this stays free text. */
export function NetworkPicker({ value, knownNetworks, onChange }: NetworkPickerProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const listId = useId();

  function commit() {
    setOpen(false);
    const trimmed = draft.trim();
    if (trimmed !== (value ?? "")) onChange(trimmed || null);
  }

  if (open) {
    return (
      <>
        <input
          autoFocus
          list={listId}
          value={draft}
          onChange={(event) => setDraft(event.target.value.toUpperCase())}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commit();
            }
            if (event.key === "Escape") setOpen(false);
          }}
          className="w-28 rounded-md border border-border bg-surface-2 px-1.5 py-0.5 text-xs text-text-primary outline-none"
        />
        <datalist id={listId}>
          {knownNetworks.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </>
    );
  }

  return (
    <button
      type="button"
      onClick={() => {
        setDraft(value ?? "");
        setOpen(true);
      }}
      title={value ?? undefined}
      className="max-w-[100px] truncate rounded px-1.5 py-0.5 text-right text-xs text-text-muted hover:bg-surface-2 hover:text-text-primary"
    >
      {value ?? t("crypto.table.addNetwork")}
    </button>
  );
}
