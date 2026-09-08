# Aurum API Documentation

Aurum exposes the same REST API its own frontend uses. Every action available in the UI — adding a
transaction, creating an account, tagging an expense, importing a CSV statement, tracking an asset,
setting a budget — can be done directly over HTTP. This makes it possible to script Aurum, feed it
from another program (a bank-sync job, a bot, a shortcut on your phone), or pull your data into your
own tools.

There is no SDK — it's a plain JSON REST API, callable with `curl`, any HTTP client library, or tools
like Postman/Insomnia.

> Interactive, always-up-to-date docs are also built into the backend itself: once your instance is
> running, open `http://<host>:<port>/api/docs` (Swagger UI) or `http://<host>:<port>/api/redoc`
> (ReDoc) for a live, "try it out" version of everything below.

## Table of Contents

- [Base URL & Authentication](#base-url--authentication)
- [Conventions](#conventions)
- [Errors](#errors)
- [Health Check](#health-check)
- [Accounts](#accounts)
- [Categories](#categories)
- [Tags](#tags)
- [Transactions](#transactions)
- [Recurring Transactions](#recurring-transactions)
- [Budgets](#budgets)
- [Goals](#goals)
- [Assets & Net Worth](#assets--net-worth)
- [Crypto](#crypto)
- [Dashboard, Cash Flow & Reports](#dashboard-cash-flow--reports)
- [Insights & Advice](#insights--advice)
- [Settings](#settings)
- [Backup & Restore](#backup--restore)
- [Recipes](#recipes)

## Base URL & Authentication

Aurum ships as three containers (Postgres, FastAPI backend, nginx-served frontend). The frontend
container reverse-proxies `/api/*` straight through to the backend, so **the API and the web UI share
the same host and port** — whatever you set `AURUM_WEB_PORT` to in `.env` (default `3000`):

```
http://<host>:<port>/api
```

For example, on a local install: `http://localhost:3000/api`. All endpoints below are relative to
this base URL — e.g. `GET /transactions` means `GET http://localhost:3000/api/transactions`.

### Auth

Aurum has no built-in login system or API keys — it's designed for one person to self-host one
private instance. Access control is whatever you put in front of it:

- **Nothing set:** if `AURUM_BASIC_AUTH_USER` / `AURUM_BASIC_AUTH_PASSWORD` are empty in `.env`
  (the default), the API is completely open to anyone who can reach the host — no credentials
  needed. Fine for `localhost`-only or a private network; **not** fine on the public internet.
- **HTTP Basic Auth:** set both `AURUM_BASIC_AUTH_USER` and `AURUM_BASIC_AUTH_PASSWORD` in `.env`
  and restart (`docker compose up -d`). Every request — UI and API alike — then requires an
  `Authorization: Basic <base64(user:password)>` header, or the equivalent `-u user:password` flag
  in curl.

```bash
# No auth configured
curl http://localhost:3000/api/accounts

# Basic Auth configured
curl -u myuser:mypassword http://localhost:3000/api/accounts
```

`GET /api/health` is always open (no auth), even with Basic Auth configured — it exists for Docker
healthchecks and uptime monitors.

There's no per-endpoint permission model beyond this: whoever can authenticate can read, create,
update, and delete everything.

## Conventions

- **Format:** all request and response bodies are JSON (`Content-Type: application/json`).
- **IDs:** integer, auto-incrementing, assigned by the server.
- **Money fields** (`amount`, `monthly_limit`, `value`, ...): decimal numbers as JSON numbers or
  strings, up to 14 digits with 2 decimal places. Aurum is single-currency per account/asset — there
  is no built-in FX conversion.
- **Dates:** `YYYY-MM-DD` (ISO 8601 date, no time component). Timestamps (e.g. backup `exported_at`)
  are full ISO 8601 datetimes.
- **Colors:** 6-digit hex strings, e.g. `"#4f46e5"`.
- **Partial updates:** every `PATCH` endpoint only touches the fields you actually send — omit a
  field and it's left unchanged. This matters for fields whose "clear this" value is `null`: sending
  `{"parent_id": null}` explicitly clears a category's parent, while omitting `parent_id` entirely
  leaves it as-is.
- **Enums** are plain lowercase strings — see each resource's table below for the valid values.

## Errors

Standard HTTP status codes:

| Code | Meaning |
|---|---|
| `200` / `201` | Success (`201` on `POST` that creates a resource) |
| `204` | Success, no response body (deletes) |
| `400` | Invalid request — a business rule was violated (e.g. wrong category kind, duplicate budget) |
| `401` | Missing/invalid Basic Auth credentials (only when Basic Auth is configured) |
| `404` | Resource not found |
| `422` | Request body failed schema validation (wrong type, missing required field, out-of-range value) |

Error bodies follow FastAPI's default shape:

```json
{ "detail": "Category 'Salary' is a income category and cannot be used for a expense transaction" }
```

`422` validation errors carry a `detail` array with one entry per invalid field instead of a single
string.

## Health Check

### `GET /api/health`

No auth required. Returns `{"status": "ok", "version": "1.1.0"}` — `version` is the running app's
version, the same value shown in the UI under Settings. Use this to check the backend is up before
hitting anything else.

## Accounts

An account is a place money lives — a bank account, a card, a cash wallet. Every transaction belongs
to exactly one account (transfers touch two). Balances are **derived** from transactions, not
stored — there's no "set balance" endpoint.

**`AccountType`:** `checking` · `debit_card` · `savings` · `credit_card` · `cash` · `investment` · `other`

| Method | Path | Description |
|---|---|---|
| `GET` | `/accounts` | List accounts, with live balance. `?include_archived=true` to include archived ones (excluded by default). |
| `POST` | `/accounts` | Create an account. |
| `PATCH` | `/accounts/{id}` | Update an account (partial). Set `is_archived: true` to archive instead of deleting. |
| `DELETE` | `/accounts/{id}` | Delete an account **and every transaction on it** — irreversible. |

**Create/update body:**

```json
{
  "name": "Checking",
  "type": "checking",
  "currency": "USD",
  "color": "#4f46e5"
}
```

- `name`: required, 1–100 chars.
- `type`: optional, defaults to `checking`.
- `currency`: optional 3-letter code, defaults to `USD`. Purely a display label — not validated
  against ISO 4217 and not used for conversion.
- `color`: optional hex color.
- `is_archived` (update only): archive/unarchive without deleting. An archived account is hidden
  from the default account list but its transactions and balance remain intact.

**Response** (`AccountWithBalance`):

```json
{
  "id": 1,
  "name": "Checking",
  "type": "checking",
  "currency": "USD",
  "color": "#4f46e5",
  "is_archived": false,
  "balance": "1523.40"
}
```

## Categories

Categories classify transactions as income or expense, with one optional level of subcategories
(a subcategory's `parent_id` points at a top-level category of the *same* kind — no deeper nesting).
A handful of default categories are seeded on first run and can't be deleted (`is_default: true`),
though they can be renamed, recolored, and reordered.

**`CategoryKind`:** `income` · `expense`

| Method | Path | Description |
|---|---|---|
| `GET` | `/categories` | List categories, sorted by `sort_order`. `?kind=income` or `?kind=expense` to filter. |
| `POST` | `/categories` | Create a category (or subcategory, via `parent_id`). |
| `PATCH` | `/categories/{id}` | Update a category (partial). |
| `DELETE` | `/categories/{id}` | Delete a category. For a default (`is_default: true`) category, fails with `400` if any transaction or transaction split still points at it — a custom category has no such guard and can always be deleted. |

**Create body:**

```json
{
  "name": "Groceries",
  "kind": "expense",
  "icon": "shopping-cart",
  "color": "#22c55e",
  "sort_order": 0,
  "parent_id": null
}
```

- `name`: required, 1–100 chars.
- `kind`: required, `income` or `expense`. Fixed at creation — there's no way to flip a category's
  kind afterward (create a new one instead).
- `icon`: optional, free-form string (the frontend maps these to an icon set).
- `color`: required hex color.
- `sort_order`: optional int controlling display order, defaults to `0`.
- `parent_id`: optional. Rules enforced server-side: the parent must itself be top-level (no
  grandchildren), must share the child's `kind`, and a category can't be its own parent.

**Update** accepts the same fields, all optional. Note: to turn a subcategory back into a top-level
category, send `"parent_id": null` explicitly — omitting the field leaves the existing parent as-is.
A category that already has subcategories of its own can't be turned into a subcategory.

**Response** (`CategoryRead`): same fields as create, plus `id` and `is_default`.

## Tags

Free-form labels a transaction can carry any number of. Case-insensitive dedup on creation: posting
`"Georgia"` when `"georgia"` already exists returns the existing tag instead of making a duplicate.

| Method | Path | Description |
|---|---|---|
| `GET` | `/tags` | List all tags, alphabetically. |
| `POST` | `/tags` | Create a tag (or return the existing one, case-insensitive match). |
| `DELETE` | `/tags/{id}` | Delete a tag — removes it from every transaction that had it. |

**Create body:** `{"name": "Vacation"}` (1–50 chars).

**Response** (`TagRead`): `{"id": 1, "name": "Vacation"}`.

## Transactions

The core resource. A transaction is `income`, `expense`, or `transfer`.

**`TransactionType`:** `income` · `expense` · `transfer`

| Method | Path | Description |
|---|---|---|
| `GET` | `/transactions` | Paginated, filterable list. See query params below. |
| `GET` | `/transactions/years` | Every year with data (plus the current year), for a year picker. Returns `[2024, 2025, 2026]`. |
| `POST` | `/transactions` | Create one transaction. |
| `POST` | `/transactions/bulk` | Create up to 5000 transactions in one all-or-nothing batch (CSV import). |
| `PATCH` | `/transactions/{id}` | Update a transaction (partial). |
| `DELETE` | `/transactions/{id}` | Delete a transaction. |

### `GET /transactions` query params

| Param | Type | Notes |
|---|---|---|
| `year` | int | `2000`–`2100` |
| `month` | int | `1`–`12` |
| `start_date` / `end_date` | date | Inclusive range, combinable with `year`/`month` |
| `account_id` | int | |
| `category_id` | int | |
| `tag_id` | int | |
| `type` | `income`\|`expense`\|`transfer` | |
| `search` | string | Substring match (case-insensitive) against description, merchant, and notes |
| `sort` | `date_desc`\|`amount_desc`\|`amount_asc` | Default `date_desc` |
| `page` | int | Default `1` |
| `page_size` | int | Default `20`, max `200` |

**Response** (`TransactionPage`):

```json
{
  "items": [ /* TransactionRead[] */ ],
  "total": 143,
  "page": 1,
  "page_size": 20
}
```

### Create body (`TransactionCreate`)

```json
{
  "account_id": 1,
  "category_id": 4,
  "transfer_account_id": null,
  "type": "expense",
  "amount": 42.50,
  "description": "Groceries",
  "merchant": "Whole Foods",
  "notes": null,
  "date": "2026-08-29",
  "tag_ids": [3, 7]
}
```

Field rules, enforced server-side:

- `account_id`: required, the account the money moves through.
- `type`: required. Drives which other fields are valid:
  - `income` / `expense`: `category_id` optional but **must** point at a category of the matching
    `kind` if given (an `income` transaction can't use an `expense` category). `transfer_account_id`
    must be omitted.
  - `transfer`: `transfer_account_id` is **required** and must differ from `account_id`.
    `category_id` must be omitted — transfers aren't categorized. `splits` aren't valid either.
- `amount`: required, `> 0` (transfers/expenses aren't signed negative — direction comes from
  `type`), up to 14 digits, 2 decimal places.
- `description`: required, 1–255 chars. Auto-capitalized server-side (first letter uppercased).
- `merchant`: optional, up to 150 chars.
- `notes`: optional, free text.
- `date`: required.
- `tag_ids`: optional list of existing tag IDs. Unknown IDs return `400`.
- `splits`: optional list of `{"category_id": ..., "amount": ..., "note": ...}` — divides the
  transaction across 2+ categories instead of one. See **Splitting a transaction** below.

**Update** (`TransactionUpdate`) accepts the same fields, all optional, plus the same
type/category/transfer/split consistency rules applied to the *effective* (merged) values. `tag_ids`:
omit to leave tags untouched; send (even `[]`) to replace the full tag set. `splits`: omit to leave
splits untouched; send (even `[]`) to replace the full split set — send `[]` together with a
`category_id` to turn a split transaction back into a normal single-category one.

**Response** (`TransactionRead`): the input fields plus `id`, and the nested `account`
(`AccountRead`), `category` (`CategoryRead` or `null`), `tags` (`TagRead[]`), `splits`
(`TransactionSplitRead[]`, empty for a normal non-split transaction).

### Splitting a transaction across categories

A single purchase that covers more than one subcategory of the same parent (a supermarket receipt
that's part "Sweets", part "Alcohol", both under "Groceries") can be recorded as one transaction
divided across those categories instead of several separate transactions:

```json
{
  "account_id": 1,
  "type": "expense",
  "amount": 84.20,
  "description": "Grocery run",
  "date": "2026-08-29",
  "splits": [
    { "category_id": 12, "amount": 60.00, "note": "Sweets" },
    { "category_id": 13, "amount": 24.20, "note": "Alcohol" }
  ]
}
```

Rules, enforced on both create and update (against the row as it would look *after* the change):

- `category_id` on the transaction itself **must be omitted** when `splits` is given — the split
  entries carry the categories instead.
- Not valid on a `transfer` transaction.
- At least 2 entries — a single split is just `category_id` with extra steps and is rejected.
- Each split's `category_id` is required and must be a category of the transaction's own kind
  (`income`/`expense`, same check a plain `category_id` gets); `amount` is required (`> 0`, up to 14
  digits/2 decimals); `note` is optional, up to 200 chars.
- **All splits must share the same top-level category** — either the parent itself (an
  unspecified-subcategory line) or one of its direct subcategories. Splitting across two unrelated
  top-level categories (e.g. part "Groceries", part "Transport") is rejected with `400`, since the
  feature exists to divide one purchase's total *within* one category tree, not to record what's
  really two separate transactions as one.
- The split amounts **must sum exactly** to the transaction's own `amount`, or the request is
  rejected with `400`.

Aggregation endpoints are split-aware: `/dashboard/summary`'s `spending_by_category` and
`/reports/category-ranking` count a split transaction's amount under every category it actually
touches (rolled up to the shared parent), not just once under a single category — a receipt split
$60/$24.20 between Sweets and Alcohol above contributes exactly those amounts to each subcategory's
total under Groceries.

### Bulk create (`POST /transactions/bulk`)

Used by the CSV import wizard, but callable directly for any bulk load (e.g. syncing from a bank
export tool). All rows are validated **before** any is inserted — one bad row fails the whole
request with no partial import.

```json
{ "items": [ /* 1–5000 TransactionCreate objects */ ] }
```

Response: `{"created": 250}`.

## Recurring Transactions

Templates for bills/income that repeat on a schedule. **Nothing posts automatically in the
background** — a transaction is only created when you call the `/post` endpoint (or click "Post" in
the UI). This is deliberate: a missed week never silently back-fills a pile of transactions.

**`RecurringFrequency`:** `weekly` · `monthly` · `yearly`

| Method | Path | Description |
|---|---|---|
| `GET` | `/recurring` | List all recurring templates, with computed due-date info. |
| `POST` | `/recurring` | Create a template. |
| `PATCH` | `/recurring/{id}` | Update a template (partial). Set `is_active: false` to pause. |
| `DELETE` | `/recurring/{id}` | Delete a template (does not touch already-posted transactions). |
| `POST` | `/recurring/{id}/post` | Create a real transaction from the template, dated today, and advance the schedule. |

**Create body:** same shape as `TransactionCreate` minus `date`/`tag_ids`, plus:

```json
{
  "account_id": 1,
  "category_id": 4,
  "type": "expense",
  "amount": 15.99,
  "description": "Netflix",
  "frequency": "monthly",
  "anchor_date": "2026-01-05"
}
```

`anchor_date` is the first due date; each `/post` call advances `last_posted_date` and recomputes
`next_due_date` (monthly clamps to the shortest month, e.g. day 31 → day 28/29/30; yearly Feb 29
falls back to Feb 28 in non-leap years).

**Response** (`RecurringTransactionRead`) adds computed fields: `next_due_date`, `is_due` (boolean),
`days_until_due` (negative if overdue), plus denormalized `account_name`/`category_name`/etc. for
display without extra lookups.

## Budgets

One monthly spending limit per **expense** category (income categories can't be budgeted; each
category can have at most one budget).

| Method | Path | Description |
|---|---|---|
| `GET` | `/budgets` | List all budgets. |
| `GET` | `/budgets/status` | Budgets vs. actual spend for a month. `?year=&month=` (default: current month). |
| `POST` | `/budgets` | Create a budget. `400` if the category already has one, or isn't an expense category. |
| `PATCH` | `/budgets/{id}` | Update `monthly_limit`. |
| `DELETE` | `/budgets/{id}` | Delete a budget. |

**Create body:** `{"category_id": 4, "monthly_limit": 500}`.

**`GET /budgets/status` response:**

```json
{
  "year": 2026,
  "month": 8,
  "items": [
    {
      "budget_id": 1,
      "category_id": 4,
      "category_name": "Groceries",
      "category_color": "#22c55e",
      "category_icon": "shopping-cart",
      "monthly_limit": "500.00",
      "spent": "612.30",
      "remaining": "-112.30",
      "percent": 122.46,
      "is_over_budget": true
    }
  ]
}
```

`percent` can exceed `100` on purpose — clamp it client-side if you're rendering a progress bar.

## Goals

Savings goals with a running contribution log. `current_amount` is always the sum of every logged
contribution — there's no separate "set balance" call.

| Method | Path | Description |
|---|---|---|
| `GET` | `/goals` | List all goals with computed progress. |
| `POST` | `/goals` | Create a goal. |
| `PATCH` | `/goals/{id}` | Update `name`/`target_amount`/`target_date` (partial). |
| `DELETE` | `/goals/{id}` | Delete a goal and its contribution log. |
| `POST` | `/goals/{id}/contributions` | Log a contribution (or a withdrawal). |

**Create body:** `{"name": "Emergency fund", "target_amount": 10000, "target_date": "2027-01-01"}`
(`target_date` optional).

**Add contribution:** `{"amount": 250, "date": "2026-08-29", "note": "Bonus"}`. `amount` may be
negative (a withdrawal against the goal) but not zero.

**Response** (`GoalRead`):

```json
{
  "id": 1,
  "name": "Emergency fund",
  "target_amount": "10000.00",
  "target_date": "2027-01-01",
  "current_amount": "3250.00",
  "remaining": "6750.00",
  "percent": 32.5,
  "is_reached": false
}
```

## Assets & Net Worth

Assets are manually tracked, non-cash net-worth components — investments, crypto, real estate,
vehicles, precious metals, etc. Cash is **not** an asset; it's derived automatically from account
balances and shows up in the net worth summary alongside assets, not as an `Asset` row.

Each asset has a value **history** (`AssetValuation` rows, one per date) rather than a single
number — creating an asset seeds its first valuation, and you add more over time to track
appreciation/depreciation.

**`AssetClass`:** `investments` · `crypto` · `real_estate` · `vehicles` · `precious_metals` · `other`
**`CapitalRole`** (how it behaves month to month — user-tagged, not inferred): `income` (e.g. a
rented-out apartment) · `neutral` (e.g. a laptop used for work) · `drain` (e.g. a depreciating
personal vehicle)
**`RiskLevel`** (risk of loss — user-tagged): `low` · `medium` · `high`

| Method | Path | Description |
|---|---|---|
| `GET` | `/assets` | List assets, each with its current (latest) value. |
| `POST` | `/assets` | Create an asset, seeding its first valuation. |
| `PATCH` | `/assets/{id}` | Update asset metadata (not its value — use the valuations endpoint). |
| `GET` | `/assets/{id}/valuations` | Full value history, oldest first. |
| `POST` | `/assets/{id}/valuations` | Record a value as of a date. Re-posting the same date **updates** that day's value (upsert) instead of erroring. |
| `DELETE` | `/assets/{id}` | Delete an asset and its whole valuation history. |
| `GET` | `/net-worth/summary` | Aggregated net worth: timeline, breakdown by class, by capital role, by risk level. |

**Create asset body:**

```json
{
  "name": "Brokerage account",
  "asset_class": "investments",
  "currency": "USD",
  "notes": null,
  "capital_role": "income",
  "monthly_cash_flow": 0,
  "risk_level": "high",
  "value": 25000,
  "as_of_date": "2026-08-29"
}
```

**Add valuation body:** `{"value": 26500, "as_of_date": "2026-08-30"}`.

**`GET /net-worth/summary`** — `?range=` one of `7d`, `30d`, `90d`, `180d`, `365d`, `all` (default
`30d`):

```json
{
  "range": "30d",
  "current": "48250.00",
  "change_amount": "1200.00",
  "change_percent": 2.55,
  "series": [ { "date": "2026-08-01", "value": "47050.00" } ],
  "breakdown": [
    { "key": "cash", "name": "Cash", "color": "#...", "icon": "wallet", "amount": "5250.00", "percent": 10.88 }
  ],
  "capital_roles": [
    { "role": "income", "label": "Income", "color": "#...", "total_value": "25000.00", "monthly_cash_flow": "0.00", "count": 1 }
  ],
  "risk_levels": [
    {
      "risk_level": "low", "label": "Low", "color": "#...",
      "total_value": "5250.00", "percent": 10.88,
      "items": [ { "key": "cash", "name": "Cash", "amount": "5250.00", "percent": 100.0 } ]
    }
  ]
}
```

## Crypto

Live-priced crypto holdings with a full buy/sell history — a CoinMarketCap-style portfolio view, kept
current against [CoinGecko](https://www.coingecko.com/en/api/pricing)'s Demo API. Under the hood each
holding **is** an Asset (`asset_class=crypto`, see [Assets & Net Worth](#assets--net-worth)) — deleting
one is `DELETE /assets/{asset_id}`, not a separate endpoint, and it shows up in `/net-worth/summary`
like any other asset automatically.

**Quantity and average buy price are never sent directly — they're derived** from a log of buy/sell
transactions, using the weighted-average-cost method: a buy blends into the running average cost; a
sell reduces quantity but leaves the average cost of what's still held unchanged. This is the same
"record events, derive the total" shape as [Goals](#goals)' contribution log.

Requires `AURUM_COINGECKO_API_KEY` in `.env` (a free Demo key, no card required). Endpoints that need
CoinGecko (`/crypto/holdings` on creation, `/crypto/refresh`, `/crypto/search`) return `400` with a
message telling you so if it's unset — adding a transaction to an existing holding never needs it at
all (see below).

Prices are **never** fetched in the background — there's no scheduler in this stack. Two triggers
only: `POST /crypto/refresh` (a manual "refresh now"), and a lazy check on every `GET
/crypto/holdings` that only actually calls CoinGecko once 24h have passed since the last successful
sync. If CoinGecko is unreachable, existing values are left untouched and `error_key` is set instead
of the whole request failing.

| Method | Path | Description |
|---|---|---|
| `GET` | `/crypto/holdings` | List holdings with live price, 1h/24h/7d % change, computed quantity/avg buy price/P&L. Also runs the lazy once-a-day auto-refresh. |
| `POST` | `/crypto/refresh` | Force a price refresh right now, bypassing the 24h window. |
| `POST` | `/crypto/holdings` | Add a new holding — its first buy transaction, inline. Fetches today's price immediately so it isn't `null` until the next sync. |
| `POST` | `/crypto/holdings/{asset_id}/transactions` | Buy more of, or sell some of, a coin already tracked. Never calls CoinGecko — value is recomputed from the last cached price. `400` if a sell would exceed what's currently held. |
| `GET` | `/crypto/holdings/{asset_id}/transactions` | Full buy/sell history for one holding, newest first. |
| `PATCH` | `/crypto/transactions/{transaction_id}` | Edit an existing transaction (partial — send only the fields you're changing). Never calls CoinGecko. `400` if changing a sell's quantity would exceed what the rest of the log leaves held. |
| `DELETE` | `/crypto/transactions/{transaction_id}` | Remove one transaction; quantity/avg buy price/value are recomputed from what's left. |
| `GET` | `/crypto/search` | `?q=` — search CoinGecko for a coin to add (name/ticker, returns its `coingecko_id` + logo). |
| `GET` | `/crypto/history` | `?range=7d\|30d\|90d\|all` (default `30d`) — total crypto holdings value over time, for the portfolio chart. No `24h` — resolution is only as dense as the sync cadence above. |

**Create body** (`POST /crypto/holdings`):

```json
{
  "coingecko_id": "bitcoin",
  "symbol": "btc",
  "name": "Bitcoin",
  "thumb_url": "https://...",
  "quantity": "0.05",
  "price_per_unit": "55000",
  "date": "2026-08-01",
  "note": null
}
```

`coingecko_id` is CoinGecko's own stable id (not the ticker — tickers collide across unrelated
coins) — get it from `/crypto/search` rather than guessing. `quantity`/`price_per_unit` support up to
18 decimal places (wei-level token amounts). `price_per_unit` is what you actually paid, in the app's
display currency — it's stored as-is, never re-derived from market data later.

**Add a transaction** (`POST /crypto/holdings/{asset_id}/transactions`):

```json
{ "type": "sell", "quantity": "0.02", "price_per_unit": "61000", "date": "2026-08-30", "note": null }
```

`type` is `"buy"` or `"sell"`.

**`GET /crypto/holdings` / `POST /crypto/refresh` response:**

```json
{
  "synced": true,
  "last_synced_at": "2026-08-30T12:00:00Z",
  "error_key": null,
  "holdings": [
    {
      "asset_id": 7,
      "coingecko_id": "bitcoin",
      "symbol": "BTC",
      "name": "Bitcoin",
      "thumb_url": "https://...",
      "quantity": "0.05",
      "avg_buy_price": "55000.00",
      "current_price": "61000.00",
      "price_change_1h": "0.12",
      "price_change_24h": "2.30",
      "price_change_7d": "-1.80",
      "value": "3050.00",
      "cost_basis": "2750.00",
      "profit_loss": "300.00",
      "profit_loss_percent": 10.91
    }
  ]
}
```

`current_price`/`value` are `null` only for a holding whose very first price fetch failed (CoinGecko
was down right when it was added) — distinct from a real `0`. `avg_buy_price`/`cost_basis`/
`profit_loss`/`profit_loss_percent` are `null` once a holding's quantity has been fully sold down to
zero (nothing left to have a cost basis). `error_key` is `"unreachable"` when a sync attempt couldn't
reach CoinGecko (existing values are kept as-is), or `null` otherwise.

**`GET /crypto/history` response:**

```json
{
  "range": "30d",
  "current": "9727.68",
  "change_amount": "1240.16",
  "change_percent": 14.6,
  "series": [
    { "date": "2026-08-01", "value": "8487.52" },
    { "date": "2026-08-02", "value": "8487.52" }
  ]
}
```

One point per calendar day, forward-filled from whatever `AssetValuation` snapshots actually exist
(same technique as `/net-worth/summary`'s own `series`, just scoped to crypto-class assets) — a day
with no sync simply repeats the last known total rather than leaving a gap. Total invested (cost
basis), all-time profit/loss, and best/worst performer aren't separate endpoints — they're trivial to
derive client-side by summing/comparing the `value`/`cost_basis`/`profit_loss_percent` fields already
in every `GET /crypto/holdings` response.

## Dashboard, Cash Flow & Reports

Read-only aggregation endpoints — the numbers behind Aurum's charts. Useful for pulling summary data
into an external dashboard without recomputing it yourself.

| Method | Path | Description |
|---|---|---|
| `GET` | `/dashboard/summary` | One month's headline numbers + spending by category. `?year=&month=` (default: current month). |
| `GET` | `/cash-flow` | Income vs. expense, month by month. `?start_date=&end_date=` (default: no bound, i.e. all history). |
| `GET` | `/reports/category-spending` | One category's spend over time. `?category_id=` (required) `&start_date=&end_date=`. |
| `GET` | `/reports/category-ranking` | All categories ranked by total spend over a period. `?kind=expense\|income` (default `expense`) `&start_date=&end_date=`. |

**`GET /dashboard/summary` response:**

```json
{
  "year": 2026, "month": 8,
  "real_income": "5200.00", "spent": "3120.45", "net": "2079.55", "transferred_out": "500.00",
  "spending_by_category": [
    { "category_id": 4, "name": "Groceries", "color": "#22c55e", "icon": "shopping-cart", "amount": "612.30", "percent": 19.6 }
  ]
}
```

**`GET /cash-flow` response:**

```json
{
  "start_date": null, "end_date": null,
  "points": [ { "year": 2026, "month": 7, "income": "5200.00", "expense": "3400.00", "net": "1800.00" } ],
  "total_income": "62400.00", "total_expense": "40800.00", "total_net": "21600.00"
}
```

## Insights & Advice

Rules-based, computed on read — no ML, no background jobs. Both read from the same transaction/
account/asset data as everything else; thresholds are configurable via [Settings](#settings).

| Method | Path | Description |
|---|---|---|
| `GET` | `/insights/alerts` | Active proactive alerts (negative cash flow streak, declining net worth, over-budget category, risky allocation, idle cash). |
| `GET` | `/advice` | Plain-language observations (rising spending categories, unbudgeted top expenses, savings-rate trend). |

Both return a `key` + machine-readable `params` per item rather than pre-rendered text — the
frontend interpolates a localized message client-side, so build your own message from `key`/`params`
if you're consuming this programmatically rather than trying to parse rendered strings.

```json
// GET /insights/alerts
{ "alerts": [ { "key": "idle_cash", "severity": "warning", "params": { "account_id": 2, "days": 75 } } ] }

// GET /advice
{ "items": [ { "key": "rising_category", "tone": "warning", "params": { "category": "Dining", "percent": 34.2 } } ] }
```

## Settings

App-wide configuration: display currency and every alert threshold used by `/insights/alerts`.
Single row, created automatically on first run — there's nothing to create, only to read/update.

| Method | Path | Description |
|---|---|---|
| `GET` | `/settings` | Read current settings. |
| `PATCH` | `/settings` | Update settings (partial). |

```json
{
  "currency": "USD",
  "negative_cash_flow_threshold_months": 2,
  "net_worth_decline_threshold_months": 2,
  "risky_allocation_threshold_percent": 20,
  "idle_cash_threshold_amount": "1000.00",
  "idle_cash_threshold_days": 60
}
```

- `currency`: 3-letter uppercase code — display-only, no conversion.
- `negative_cash_flow_threshold_months` / `net_worth_decline_threshold_months`: consecutive months
  before the corresponding alert fires (`1`–`24`).
- `risky_allocation_threshold_percent`: max % of total capital allowed in medium/high risk tiers
  before `risky_allocation_exceeded` fires (`1`–`100`).
- `idle_cash_threshold_amount` / `idle_cash_threshold_days`: balance + days of no activity a
  depository account needs to hit before `idle_cash` fires.

## Backup & Restore

A full snapshot of every table as one JSON document — the same mechanism the in-app Settings →
Backup & Restore uses. Good for scripted off-site backups, or for migrating data programmatically.

| Method | Path | Description |
|---|---|---|
| `GET` | `/backup/export` | Download a full backup as JSON. |
| `POST` | `/backup/import` | Restore from a backup file — **replaces existing data**, all-or-nothing. |

```bash
# Export
curl -u user:pass http://localhost:3000/api/backup/export -o aurum-backup.json

# Restore
curl -u user:pass -X POST http://localhost:3000/api/backup/import \
  -H "Content-Type: application/json" \
  -d @aurum-backup.json
```

The payload includes an `aurum_backup_version` field checked on import — a file from an incompatible
future format is rejected outright rather than partially applied. Treat `/backup/import` as
destructive: back up your current data first if you're experimenting.

## Recipes

### Add an expense transaction

```bash
curl -u user:pass -X POST http://localhost:3000/api/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "category_id": 4,
    "type": "expense",
    "amount": 12.50,
    "description": "Coffee",
    "date": "2026-08-30"
  }'
```

### Add income with a tag

```bash
# 1. Find or create the tag
curl -u user:pass -X POST http://localhost:3000/api/tags \
  -H "Content-Type: application/json" -d '{"name": "Freelance"}'
# -> {"id": 9, "name": "Freelance"}

# 2. Create the transaction referencing it
curl -u user:pass -X POST http://localhost:3000/api/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "category_id": 2,
    "type": "income",
    "amount": 800,
    "description": "Client invoice",
    "date": "2026-08-30",
    "tag_ids": [9]
  }'
```

### Move money between two of your own accounts

```bash
curl -u user:pass -X POST http://localhost:3000/api/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "transfer_account_id": 2,
    "type": "transfer",
    "amount": 500,
    "description": "Move to savings",
    "date": "2026-08-30"
  }'
```

### Pull this month's spend by category (for an external dashboard)

```bash
curl -u user:pass "http://localhost:3000/api/dashboard/summary" | jq '.spending_by_category'
```

### Bulk-import transactions from your own data source

```bash
curl -u user:pass -X POST http://localhost:3000/api/transactions/bulk \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      { "account_id": 1, "type": "expense", "amount": 9.99, "description": "Spotify", "date": "2026-08-01" },
      { "account_id": 1, "type": "expense", "amount": 45.00, "description": "Gas", "date": "2026-08-03" }
    ]
  }'
```

---

For self-hosting, environment variables, and running Aurum itself, see [README.md](README.md).
