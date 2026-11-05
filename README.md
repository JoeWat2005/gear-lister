# gear-lister

Lists the same gear on **Reverb** (fixed price + offers, as drafts) and **eBay UK** (auction or fixed price) from one spreadsheet.

Reverb has no auction format, so Reverb listings are always fixed-price with "offers" on.
eBay has no public draft API, so for eBay the script either **verifies** (eBay checks every item, lists nothing)
or **schedules** the listings to go live at a time you choose. Scheduled listings appear in Seller Hub under
*Listings > Scheduled* and you can edit or delete them before they start. That is the closest thing eBay offers to a draft.

## One-time setup

```
pip install -r requirements.txt
copy .env.example .env
```

### Reverb
1. reverb.com > Settings > **API & Integrations** > Personal Access Tokens > create one with `write_listings` and `read_profile`.
2. Put it in `.env` as `REVERB_TOKEN`.
3. `python reverb_setup.py` should print your account. Use `python reverb_setup.py --find "solid body"` to get category slugs.

### eBay
1. Sign up at developer.ebay.com (free). Create a **Production** keyset. Copy App ID → `EBAY_CLIENT_ID`, Cert ID → `EBAY_CLIENT_SECRET`, Dev ID → `EBAY_DEV_ID`.
2. On the *User Tokens* page choose *Get a Token from eBay via Your Application*, add an eBay Redirect URL (any accept URL is fine) and copy the **RuName** → `EBAY_RUNAME`.
3. `python ebay_auth.py` opens a consent link. Sign in with your selling account, click Agree, paste the redirected URL back. This saves `.ebay_token.json` (refreshes itself for ~18 months).
4. `python ebay_policies.py` prints your business policy IDs. Put them in `.env`. (Create them in Seller Hub > Account > Business policies if you have none.)
5. `python ebay_categories.py --find "electric guitar"` gives `ebay_category_id` values.

**Postage policies:** eBay listings use business policies. `EBAY_SHIPPING_POLICY_ID` is the default (collection only).
`EBAY_SHIPPING_POLICY_SMALL_ID` / `_MEDIUM_ID` / `_LARGE_ID` are optional flat-rate courier tiers (buyer pays, collection still
offered) chosen per row with the `ebay_postage` column. Create or edit them in Seller Hub > Account > Business policies, or
change the flat rate there at any time; listings pick up the policy by ID.

**Syncing prices back to Reverb:** `python update_reverb_prices.py --from-bin` previews setting each Reverb listing's price to the
eBay `buy_it_now_gbp` column; add `--apply` to push it.

**Relisting on Reverb:** `python relist_reverb.py` previews relisting every ended Reverb listing (and publishing the drafts) at
the live eBay Buy It Now price, skipping anything sold on eBay; add `--apply` to do it. It goes one listing every 45-75 s on
purpose: about 30 fast API edits got the account flagged by Reverb's automated checks on 30 Oct.

**Testing against the eBay sandbox:** put your Sandbox keyset in `EBAY_SANDBOX_CLIENT_ID` / `EBAY_SANDBOX_CLIENT_SECRET` / `EBAY_SANDBOX_RUNAME`
and set `EBAY_ENV=sandbox`. The sandbox needs its own test user (developer.ebay.com > Sandbox > Register a test user) and its own
`python ebay_auth.py` sign-in, saved to `.ebay_token.sandbox.json`. Set `EBAY_ENV=production` again to go live.

## How are the eBay auctions going?

```
python ebay_status.py          # bids, current price, reserve met?, watchers, time left for every active listing
python ebay_status.py --sold   # also items sold in the last 60 days
python ebay_status.py --csv    # also writes out/ebay_status.csv
```

## Already have listings on Reverb? Pull them in

```
python pull_reverb.py                  # all your listings incl. drafts, needs REVERB_TOKEN
python pull_reverb.py --shop <slug>    # live listings only, no token (slug from reverb.com/shop/<slug>)
```

This fills title, make, model, year, finish, condition, description, price, category, postage and the
Reverb-hosted photo URLs for every listing, and marks them as already on Reverb so they are not duplicated.
You then only add `ebay_category_id` and `auction_start_gbp` per row before listing on eBay.

## Fill in items.csv

38 rows are pre-created (ITEM-001 to ITEM-038). `items.example.csv` shows two filled-in rows. Rows with an empty title are ignored.

| column | required | notes |
|---|---|---|
| sku | yes | any unique code, used to track what has been listed |
| title | yes | max 80 chars on eBay |
| make, model | yes | Reverb refuses to publish without them |
| condition | yes | `brand-new`, `b-stock`, `mint`, `excellent`, `very-good`, `good`, `fair`, `poor`, `non-functioning` |
| description | | plain text |
| price_gbp | yes | Reverb price, and eBay price when `ebay_format=fixed` |
| reverb_category | yes | slug from `reverb_setup.py --find` |
| ebay_category_id | yes | number from `ebay_categories.py --find` |
| photos | yes | public https URLs separated by `\|` (see photos section) |
| shipping_gb_gbp / shipping_everywhere_gbp | | Reverb postage rates (ignored if `REVERB_SHIPPING_PROFILE_ID` is set) |
| ebay_format | | `auction` (default) or `fixed` |
| auction_start_gbp | for auctions | starting bid |
| reserve_gbp, buy_it_now_gbp | | optional auction extras |
| ebay_duration | | `Days_1/3/5/7/10` for auctions, default `Days_7` |
| ebay_postage | | `collection` (default), `small`, `medium` or `large`: which eBay postage policy to use, see below |
| ebay_title | | optional shorter title used only on eBay (80 char max); blank = use `title` |
| ebay_specifics | | extra item specifics, e.g. `Type=Electric Guitar;Body Type=Solid` (eBay rejects listings missing required ones, the verify run tells you which) |
| list_on_reverb / list_on_ebay | | `yes`/`no` |

### Photos
Both sites fetch photos from URLs. If yours are on your PC, drop them in `photos/ITEM-001/`, `photos/ITEM-002/` ... and run
`python upload_photos.py`. It uploads to eBay's picture host and writes the public URLs into `items.csv`, which Reverb can also read.

## Listing

```
python list_reverb.py --dry-run         # show the payloads, send nothing
python list_reverb.py                   # create Reverb DRAFTS -> review at reverb.com/my/selling/drafts
python list_reverb.py --publish         # or publish straight away

python list_ebay.py                     # eBay VERIFIES every item, lists nothing, shows fees + missing fields
python list_ebay.py --schedule 2026-11-07T19:00:00   # list now, auctions start Sat 7pm UK time
python list_ebay.py --go                # list immediately

python list_all.py                      # Reverb drafts + eBay verify in one go
python list_all.py --ebay-schedule 2026-11-07T19:00:00
```

Add `--sku ITEM-003` to any command to do one item. Every created listing is logged in `out/results.csv`
and re-runs skip items already created there (`--force` overrides).

To try eBay without real listings set `EBAY_ENV=sandbox` with a sandbox keyset and a sandbox test user.
For Reverb set `REVERB_SANDBOX=true` with a sandbox.reverb.com token.
