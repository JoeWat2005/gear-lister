# gear-lister

A Python command-line tool that lists the same music gear on Reverb and eBay UK from one spreadsheet.

Reverb has no auction format, so Reverb listings are always fixed price (with offers on by default) and are created as drafts unless you choose to publish. eBay has no public draft API, so for eBay the tool either **verifies** (eBay checks every item and nothing is listed) or **schedules** listings to go live at a time you choose. Scheduled listings appear in Seller Hub under *Listings > Scheduled*, where you can edit or delete them before they start. That is the closest thing eBay offers to a draft.

## Features

- Creates Reverb listings from `items.csv`, as drafts or published straight away.
- Creates eBay UK auctions or fixed-price listings: verify only, schedule for a UK start time, or list immediately. Supports reserve and Buy It Now prices, item specifics and business policies, including optional postage tiers.
- Imports your existing Reverb listings, photos included, into `items.csv`.
- Uploads local photos to eBay's picture service and writes the public URLs back into `items.csv`, where Reverb can use them too.
- Reports live eBay listing status: bids, current price, whether the reserve is met, watchers and time left, plus items sold in the last 60 days.
- Keeps Reverb in step with eBay: pushes price changes, relists ended Reverb listings at the live eBay Buy It Now price, and matches Reverb UK delivery to the eBay postage tier.
- Logs every created listing in `out/results.csv`, so re-runs skip items that are already done.
- Works against the eBay and Reverb sandboxes for testing.

## Tech stack

- Python 3.10+
- `requests` and `python-dotenv`
- Reverb API
- eBay Trading API (XML) for verifying, adding and reading listings; eBay OAuth user tokens; the Sell Account API for business policies; the Commerce Taxonomy API for category suggestions; and the Commerce Media API for photo uploads
- Pillow (optional): if installed, phone photos are rotated using their EXIF orientation before upload

## Getting started

### Prerequisites

- Python 3.10 or newer. The code uses `X | None` type hints, which need 3.10.
- A Reverb account and a personal access token.
- An eBay developer account with a Production keyset, and an eBay seller account with business policies for payment, returns and postage.

### Installation

```
pip install -r requirements.txt
copy .env.example .env
```

`copy` is the Windows command; use `cp` on macOS or Linux. Run every script from the repository root.

### Reverb setup

1. On reverb.com, go to Settings > **API & Integrations** > Personal Access Tokens and create a token with `write_listings` and `read_profile`.
2. Put it in `.env` as `REVERB_TOKEN`.
3. `python reverb_setup.py` should print your account, the condition values and your shipping profiles. Use `python reverb_setup.py --find "solid body"` to look up category slugs.

### eBay setup

1. Sign up at developer.ebay.com (free) and create a **Production** keyset. Copy App ID to `EBAY_CLIENT_ID`, Cert ID to `EBAY_CLIENT_SECRET` and Dev ID to `EBAY_DEV_ID`.
2. On the *User Tokens* page, choose *Get a Token from eBay via Your Application*, add an eBay Redirect URL (any accept URL is fine) and copy the **RuName** to `EBAY_RUNAME`.
3. Run `python ebay_auth.py`. It prints a consent link: sign in with your selling account, click Agree, and paste the redirected URL back (or pass it as an argument: `python ebay_auth.py "<redirected URL>"`). This saves `.ebay_token.json`, which refreshes itself for about 18 months.
4. Run `python ebay_policies.py` to print your business policy IDs, and put them in `.env`. If you have none, create them in Seller Hub > Account > Business policies.
5. Run `python ebay_categories.py --find "electric guitar"` to find `ebay_category_id` values.

**Postage policies:** eBay listings use business policies. `EBAY_SHIPPING_POLICY_ID` is the default (collection only). `EBAY_SHIPPING_POLICY_SMALL_ID`, `EBAY_SHIPPING_POLICY_MEDIUM_ID` and `EBAY_SHIPPING_POLICY_LARGE_ID` are optional flat-rate courier tiers (buyer pays, collection still offered), chosen per row with the `ebay_postage` column. You can create them, or change the flat rate at any time, in Seller Hub > Account > Business policies; listings pick up the policy by ID.

### Environment variables

All settings live in `.env` (see `.env.example`).

| Variable | Purpose |
|---|---|
| `REVERB_TOKEN` | Reverb personal access token |
| `REVERB_SANDBOX` | Set to `true` to use sandbox.reverb.com with a sandbox token |
| `REVERB_CURRENCY` | Currency for Reverb prices |
| `REVERB_SHIPPING_PROFILE_ID` | Optional saved Reverb shipping profile, used instead of per-item rates |
| `EBAY_ENV` | `production` or `sandbox` |
| `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` | App ID and Cert ID from the Production keyset |
| `EBAY_DEV_ID` | Dev ID from the keyset (read into the config, but no current call uses it) |
| `EBAY_RUNAME` | RuName used for the OAuth sign-in |
| `EBAY_SANDBOX_CLIENT_ID`, `EBAY_SANDBOX_CLIENT_SECRET`, `EBAY_SANDBOX_RUNAME` | Sandbox keyset, used when `EBAY_ENV=sandbox` |
| `EBAY_PAYMENT_POLICY_ID`, `EBAY_RETURN_POLICY_ID`, `EBAY_SHIPPING_POLICY_ID` | Business policy IDs, required for eBay listings |
| `EBAY_SHIPPING_POLICY_SMALL_ID`, `EBAY_SHIPPING_POLICY_MEDIUM_ID`, `EBAY_SHIPPING_POLICY_LARGE_ID` | Optional postage tiers chosen with `ebay_postage` |
| `EBAY_POSTCODE` | Item location |
| `EBAY_SITE_ID`, `EBAY_SITE_NAME`, `EBAY_MARKETPLACE_ID`, `EBAY_CURRENCY`, `EBAY_COUNTRY` | Marketplace settings; the defaults target ebay.co.uk, so leave them unless you sell elsewhere |

### Fill in items.csv

`items.csv` is the working spreadsheet that the scripts read and update. `items.example.csv` shows two filled-in rows. Rows with an empty title are ignored, and the scripts stop with a list of problems if any row fails validation.

| Column | Required | Notes |
|---|---|---|
| `sku` | yes | Any unique code, used to track what has been listed |
| `title` | yes | Truncated to 80 characters on eBay |
| `make`, `model` | yes | Reverb refuses to publish without them |
| `year`, `finish` | | Also sent to eBay as the Year and Colour item specifics |
| `condition` | yes | `brand-new`, `b-stock`, `mint`, `excellent`, `very-good`, `good`, `fair`, `poor` or `non-functioning` |
| `description` | | Plain text |
| `price_gbp` | yes | Reverb price, and the eBay price when `ebay_format=fixed` |
| `reverb_category` | yes | Slug from `reverb_setup.py --find` |
| `ebay_category_id` | yes | Number from `ebay_categories.py --find` |
| `photos` | yes | Public https URLs separated by `\|` (see Photos below) |
| `shipping_gb_gbp`, `shipping_everywhere_gbp` | | Reverb postage rates (ignored if `REVERB_SHIPPING_PROFILE_ID` is set) |
| `offers_enabled` | | `yes`/`no` for Reverb offers (default `yes`) |
| `ebay_format` | | `auction` (default) or `fixed` |
| `auction_start_gbp` | for auctions | Starting bid |
| `reserve_gbp`, `buy_it_now_gbp` | | Optional auction extras |
| `ebay_duration` | | `Days_1`, `Days_3`, `Days_5`, `Days_7` or `Days_10` for auctions (default `Days_7`); fixed-price listings run until cancelled |
| `quantity` | | Default 1; auctions always list a quantity of 1 |
| `ebay_postage` | | `collection` (default), `small`, `medium` or `large`: which eBay postage policy to use |
| `ebay_title` | | Optional shorter title used only on eBay (80 characters max); blank means use `title` |
| `ebay_specifics` | | Extra item specifics, for example `Type=Electric Guitar;Body Type=Solid`. eBay rejects listings that are missing required specifics; the verify run tells you which |
| `list_on_reverb`, `list_on_ebay` | | `yes`/`no` (default `yes`) |

### Photos

Both sites fetch photos from URLs. If your photos are on your computer, put them in `photos/ITEM-001/`, `photos/ITEM-002/` and so on, then run:

```
python upload_photos.py              # skips SKUs that already have photo URLs
python upload_photos.py --overwrite  # replace existing URLs
```

It uploads each SKU's photos (sorted by file name, up to 24) to eBay's picture service and writes the public URLs into `items.csv`, which Reverb can also read. Uploaded images that are not used in a listing within 30 days expire.

## Usage

### Listing

```
python list_reverb.py --dry-run         # show the payloads, send nothing
python list_reverb.py                   # create Reverb drafts; review them at reverb.com/my/selling/drafts
python list_reverb.py --publish         # or publish straight away

python list_ebay.py                     # eBay verifies every item, lists nothing, shows fees and missing fields
python list_ebay.py --schedule 2026-11-07T19:00:00   # list now; the listings start at that UK time
python list_ebay.py --go                # list immediately

python list_all.py                      # Reverb drafts and eBay verify in one go
python list_all.py --ebay-schedule 2026-11-07T19:00:00
python list_all.py --ebay-go --reverb-publish
```

Add `--sku ITEM-003` (repeatable) to `list_reverb.py`, `list_ebay.py`, `list_all.py`, `update_reverb_prices.py` or `relist_reverb.py` to work on specific items. Every created listing is logged in `out/results.csv`, and re-runs of `list_reverb.py` and `list_ebay.py` skip items already created there unless you pass `--force`.

### Checking eBay listings

```
python ebay_status.py          # bids, current price, reserve met?, watchers and time left for every active listing
python ebay_status.py --sold   # also items sold in the last 60 days
python ebay_status.py --csv    # also write out/ebay_status.csv
```

### Importing existing Reverb listings

```
python pull_reverb.py                    # all your listings, including drafts; needs REVERB_TOKEN
python pull_reverb.py --state live       # live, draft, ended, sold or all (default)
python pull_reverb.py --shop <slug>      # public live listings only, no token needed (slug from reverb.com/shop/<slug>)
python pull_reverb.py --out pulled.csv   # write somewhere other than items.csv
```

This fills in the title, make, model, year, finish, condition, description, price, category, postage and the Reverb-hosted photo URLs for every listing, and marks them as already on Reverb so they are not duplicated. You then only need to add `ebay_category_id` and `auction_start_gbp` to each row (or set `ebay_format=fixed`) before listing on eBay.

### Keeping Reverb in step with eBay

```
python update_reverb_prices.py                        # preview old -> new price for every row that differs
python update_reverb_prices.py --apply                # push the price_gbp column to Reverb
python update_reverb_prices.py --percent -10 --apply  # ignore the CSV and change every price by -10%
python update_reverb_prices.py --from-bin --apply     # use the eBay buy_it_now_gbp column as the Reverb price
```

Add `--live-only` to skip drafts and ended listings.

```
python relist_reverb.py                 # preview relisting ended Reverb listings and publishing drafts
python relist_reverb.py --apply         # do it, one listing every 45-75 seconds
python relist_reverb.py --apply --delay 20
```

`relist_reverb.py` uses the live eBay Buy It Now price for each SKU (items without one keep their Reverb price) and skips anything that has sold on eBay or has `list_on_reverb=no`. Live listings stay live; only their price is corrected. The gap between listings is deliberate: on 30 Oct about 30 API edits in 16 seconds got the account flagged by Reverb's automated checks. The run stops at the first "under review" refusal.

```
python set_reverb_shipping.py           # preview
python set_reverb_shipping.py --apply   # update, 45-75 seconds between listings
```

`set_reverb_shipping.py` sets Reverb UK delivery to match each row's `ebay_postage` tier (small £12, medium £30, large £50) and keeps local pickup on.

### Testing against the sandboxes

- **eBay:** put your Sandbox keyset in `EBAY_SANDBOX_CLIENT_ID`, `EBAY_SANDBOX_CLIENT_SECRET` and `EBAY_SANDBOX_RUNAME`, and set `EBAY_ENV=sandbox`. The sandbox needs its own test user (developer.ebay.com > Sandbox > Register a test user) and its own `python ebay_auth.py` sign-in, saved to `.ebay_token.sandbox.json`. Set `EBAY_ENV=production` again to go live.
- **Reverb:** set `REVERB_SANDBOX=true` and use a sandbox.reverb.com token.

## How it works

The top-level scripts are thin command-line wrappers around the `gearlister` package:

- `gearlister/config.py` loads `.env` from the repository root. Setting `EBAY_ENV=sandbox` switches the keyset and the token file.
- `gearlister/items.py` reads `items.csv`, validates each row (condition, eBay format, make and model, auction start price, photos) and maps each condition to a Reverb condition and an eBay condition ID.
- `gearlister/reverb.py` wraps the Reverb API: account details, conditions, categories, shipping profiles, listing payloads, creating and updating listings, and paginated listing reads.
- `gearlister/ebay.py` handles eBay OAuth (consent link, code exchange, token refresh and app tokens), builds the item XML (title, prices, condition, photos, item specifics, business policies and schedule time), calls the Trading API (`VerifyAddItem`, `AddItem`, `GetMyeBaySelling`), uploads pictures and calls the REST APIs for business policies and category suggestions.
- `gearlister/state.py` appends every created, scheduled, published or failed listing to `out/results.csv`, which the scripts read to skip finished items.

The flow is: `items.csv` → validation → Reverb payload or eBay item XML → API call → `out/results.csv`.

## Project structure

```
.
├── gearlister/              # config, items.csv parsing, Reverb and eBay clients, results log
├── list_reverb.py           # create Reverb drafts or published listings
├── list_ebay.py             # verify, schedule or create eBay listings
├── list_all.py              # run both listing scripts
├── ebay_status.py           # live eBay listing status and recent sales
├── pull_reverb.py           # import existing Reverb listings into items.csv
├── upload_photos.py         # upload local photos and write the URLs into items.csv
├── update_reverb_prices.py  # push price changes to Reverb
├── relist_reverb.py         # relist ended Reverb listings at the eBay Buy It Now price
├── set_reverb_shipping.py   # match Reverb UK delivery to the eBay postage tier
├── reverb_setup.py          # check the Reverb token and look up conditions and categories
├── ebay_auth.py             # one-off eBay OAuth sign-in
├── ebay_policies.py         # print eBay business policy IDs
├── ebay_categories.py       # suggest eBay category IDs
├── items.csv                # working spreadsheet
├── items.example.csv        # two example rows
├── .env.example             # environment template
└── requirements.txt
```

Created locally and ignored by Git: `.env`, `.ebay_token*.json`, `out/` and `photos/`.

## Notes

- `list_ebay.py --schedule` uses Python's `zoneinfo` for UK time. On Windows this needs the `tzdata` package, which `requirements.txt` does not include.
