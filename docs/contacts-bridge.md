# Contacts ↔ Module Bridge

> Added in **v3117** — wires the Contacts directory together with
> module-specific entities (PropDev Lead/Buyer, Broker, Vendor, …)
> so the Contacts module is the **single source of truth** for
> person data.

## Why a bridge?

The Contacts module already knows everything we care about for a
person: `first_name`, `last_name`, `primary_email`, `primary_phone`,
`address`, `vat_number`, `country_code`. PropDev's `Lead` and
`Buyer` rows used to repeat all of those fields — which meant editing
a buyer's phone in the PropDev tab left the Contacts directory
stale, and importing a Lead from a web form did not show up in the
CRM contact list.

The bridge keeps the schema for module-specific data on the module
entity (`lead_score`, `buyer_status`, `contract_value`, `deposit_*`,
…) but moves the **canonical person columns** under the Contact row,
referenced by a nullable `contact_id` FK.

## Data model

```
oe_contacts_contact
├── id
├── first_name / last_name / company_name
├── primary_email / primary_phone / country_code / address
├── module_tags        ← JSON list: ["property_dev_lead", "property_dev_buyer", "broker"]
└── custom_properties  ← JSON dict: {"property_dev": {"preferred_contact_method": "email"}}

oe_property_dev_lead
├── id
├── source / lead_score / status / nurture_stage   ← lead-specific
├── budget_min / budget_max / currency
└── contact_id  → FK to oe_contacts_contact.id (nullable)

oe_property_dev_buyer
├── id
├── status / contract_value / deposit_amount / freeze_deadline   ← buyer-specific
├── contract_signed_at / deposit_paid_at
└── contact_id  → FK to oe_contacts_contact.id (nullable)
```

Both `module_tags` and `custom_properties` carry `server_default`
values (`'[]'` / `'{}'`) so existing rows backfill correctly on
upgrade. The contact_id column is nullable to keep legacy rows
(pre-v3117) and portal-anonymous buyers working unchanged.

## Tag values

`module_tags` is a JSON array. A single contact can carry **multiple**
tags simultaneously — a person who started as a Lead and later
signed a Buyer contract keeps **both** `property_dev_lead` and
`property_dev_buyer`. Canonical values (in
`app.modules.contacts.bridge.KNOWN_MODULE_TAGS`):

| Tag | Set when … |
|-----|------------|
| `property_dev_lead` | A PropDev Lead is created or its email matches an existing Contact |
| `property_dev_buyer` | A PropDev Buyer is created or its email matches an existing Contact |
| `broker` | (Reserved) Broker row created |
| `vendor` | (Reserved) Vendor row created |
| `subcontractor` | (Reserved) Subcontractor row created |

Third-party modules add their own tag value without a registry
update — the column is permissive on purpose.

## Synchronisation flow

### Lead/Buyer create → Contact

When `PropertyDevService.create_lead()` / `create_buyer()` runs with
`sync_to_contacts=True` (the default for UI-driven flows) the bridge:

1. Searches `oe_contacts_contact` for an active row with matching
   `primary_email`, **scoped to the caller's tenant**. Cross-tenant
   matches are intentionally ignored — emails collide globally but
   data belongs to a tenant.
2. If found: appends the appropriate tag to `module_tags`
   (idempotent), back-fills any empty canonical fields the lead/buyer
   form provided, and links via `lead.contact_id` / `buyer.contact_id`.
3. If not: creates a fresh Contact in the caller's tenant with the
   lead/buyer's name / email / phone, the appropriate tag, and links.

### Lead/Buyer update → Contact

When the user edits a Lead/Buyer's `full_name` / `email` / `phone`
via the PropDev UI, `update_lead()` / `update_buyer()` invokes the
bridge's `mirror_*_fields_to_contact()` helpers to write the new
values back to the linked Contact. The Contact stays the source of
truth; the PropDev forms are simply UI surface for editing it.

### Contact → Lead/Buyer (explicit conversion)

From the Contacts module the user can click "Convert to Lead" or
"Convert to Buyer". The corresponding routes:

* `POST /v1/contacts/{id}/convert-to-lead`
* `POST /v1/contacts/{id}/convert-to-buyer`

Each takes a small JSON payload (lead_score / source / notes /
development_id / plot_id) and creates the PropDev row with
`contact_id` already set. The Contact picks up the tag the same way
as the create-from-PropDev path.

### Reverse lookup

The Contact detail drawer fetches all linked module rows via:

* `GET /v1/contacts/{id}/module-rows`

The response shape is:

```json
{
  "property_dev_leads":  [{"id": ..., "status": ..., "lead_score": ..., ...}],
  "property_dev_buyers": [{"id": ..., "status": ..., "contract_value": ..., ...}]
}
```

Future modules add new keys (e.g. `brokers`, `vendors`) — keep keys
stable so the frontend can switch on them.

### Lead/Buyer → Contact (forward lookup)

* `GET /v1/property-dev/leads/{id}/contact` → 200 with contact
  payload when linked, 404 when not.
* `GET /v1/property-dev/buyers/{id}/contact` → ditto.

## Frontend integration

### Lead / Buyer table rows

When `row.contact_id` is set, a small `UserCircle2` icon appears next
to the name — clicking the row opens the Lead/Buyer detail drawer
where the **Linked Contact** card surfaces the canonical name +
module tags + a deep link into `/contacts`.

### Create Lead / Buyer modal

A **Sync to Contacts directory** checkbox (default ON) controls the
`sync_to_contacts` query parameter on the create endpoint. Users
toggle it off only for portal-driven anonymous signups where the
person hasn't formally identified themselves yet.

### Contacts card

The Contact card in `/contacts` shows `module_tags` as small blue
badges so users can spot at a glance whether a contact is a Lead, a
Buyer, both, etc. Filtering by tag uses the existing tag chip strip
(also indexed via the substring-match path in
`ContactRepository.list`).

## Tenancy & IDOR

The bridge follows the same tenant-scope rule as
`ContactRepository._tenant_scope`:

* A Lead / Buyer created by user A only matches Contacts whose
  `tenant_id == A` (or whose `created_by == A` for legacy rows).
* A lookup-collision across tenants (same email, different tenants)
  **creates a fresh contact** in the caller's tenant rather than
  leaking the existence of user B's row.
* The `POST /contacts/{id}/convert-to-*` routes invoke
  `_require_contact_access` first, so cross-tenant conversion is
  blocked at the perimeter.

## Tests

`backend/tests/unit/test_contact_module_bridge.py` covers:

1. Lead create → fresh Contact with `property_dev_lead` tag.
2. Buyer create with an existing matching email → link, no duplicate.
3. Lead → Buyer for same email → contact carries **both** tags.
4. Update Lead.email → Contact.primary_email mirrors.
5. Cross-tenant guard: same email, different tenants → two rows.
6. Reverse lookup returns both Lead + Buyer payloads.
7. Email-less Lead still produces a Contact.

## Why nullable FK?

`contact_id` is intentionally **nullable** for three reasons:

1. **Legacy rows** (pre-v3117) — the migration adds the column but
   does **not** backfill it. Existing Lead/Buyer rows continue to
   work with their own `full_name` / `email` until they are next
   edited via the UI.
2. **Portal-anonymous signups** — the buyer portal may legitimately
   want to create a Buyer row without exposing personal data to the
   internal Contacts directory until the user formally identifies
   themselves.
3. **Bridge failures are best-effort** — if the Contact insert
   somehow fails (network blip on remote DB, validation rejection
   in custom rules) we log the error but still return the
   Lead/Buyer to the caller. The bridge can be re-run on the next
   PATCH.

## Adding a new module to the bridge

To hook a new module (e.g. `oe_broker_module`) up:

1. Add a column `contact_id: Mapped[uuid.UUID | None]` to your
   module's main person-bearing model with `ForeignKey("oe_contacts_contact.id", ondelete="SET NULL")`.
2. Add an alembic migration following the `v3117_contact_module_bridge.py`
   pattern (inspector-guarded `add_column`).
3. In your module's `service.create_*()` invoke
   `app.modules.contacts.bridge.ensure_contact_for_person()` passing
   your module-tag string.
4. Surface the new tag string in `KNOWN_MODULE_TAGS` (cosmetic — the
   bridge accepts any string) and add a localised label key
   `contacts.module_tag_<your_tag>` to the EN locale.
5. Optionally extend `list_module_rows_for_contact()` to surface
   your rows in the reverse lookup.

## See also

* `backend/app/modules/contacts/bridge.py` — the bridge service.
* `backend/app/modules/contacts/router.py` — `POST /convert-to-lead`, `POST /convert-to-buyer`, `GET /module-rows`.
* `backend/alembic/versions/v3117_contact_module_bridge.py` — schema.
* `backend/tests/unit/test_contact_module_bridge.py` — test suite.
