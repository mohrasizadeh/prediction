"""legal_pages.py -- starter Terms, Privacy and About pages (docs/36 C2).

The footer, the sign-up form and the cookie banner link to /legal/terms, /legal/privacy and /legal/about.
Without content those links answered 404, so visitors were asked to accept Terms that did not exist.

seed() inserts these pages only when a slug is missing. It never overwrites a page an admin has saved.
Seeded pages carry starter=True. alerts.evaluate() keeps an admin alert open until every legal page has been
reviewed and saved in Admin -> Pages (saving clears starter). This text is a starting point written for a
Canada + US launch, not legal advice: have it reviewed before launch.

Words follow docs/03 section 2. The only betting word allowed is the exact disclaimer sentence.
"""
from __future__ import annotations

from datetime import datetime, timezone

DISCLAIMER = "Statistical analysis for information and entertainment. Not betting advice."
LEGAL_SLUGS = ("terms", "privacy", "about")

TERMS = f"""These terms apply when you use this site and its services. By creating an account or using the site you accept them.

## Who can use the site

You must be at least 18 years old to create an account or use the site. If the law where you live sets a higher age for using services like this one, that higher age applies to you. We may close an account if we learn the holder is under age.

## What the site is

The site shows football statistics and forecasts: the chance that a player or team reaches a stat line, and the reasons behind each forecast. {DISCLAIMER}

- Forecasts are estimates. A forecast of 70% means we expect the line to be reached about 7 times in 10, not every time.
- We publish how our forecasts did on the Track Record page, including the ones that were not reached.
- We do not show prices from sellers, link to sellers, or tell anyone what to do with a forecast.
- Decisions you make using the site are your own responsibility.

## Your account

- Keep your password private and turn on two-step sign-in if you can.
- Tell us through the Contact page if you think someone else has used your account.
- One person per account. Do not share, sell or transfer accounts.

## Plans and payment

- Paid plans are billed in advance through Stripe and **renew automatically** at the price shown when you subscribed, for the same period, until you cancel.
- A free trial, when offered, turns into a paid plan at the end of the trial unless you cancel before it ends.
- You can cancel at any time in Account > Billing. Your plan stays active until the end of the period you paid for.
- We tell you before a price change takes effect, and you can cancel before it applies.

## Fair use

Do not copy the site's data in bulk, scrape it, resell it, or try to get around plan limits, security controls or rate limits.

## Availability and changes

We work to keep the site running and the data current, but we cannot promise it will always be available, complete or error free. We may change or stop features. If we change these terms in a way that matters, we will tell signed-in users before the change applies.

## Limits on our responsibility

To the extent the law allows, the site is provided "as is" and we are not responsible for losses that come from relying on a forecast or on the data. Nothing in these terms removes rights you have under the consumer protection law where you live.

## Contact

Questions about these terms: use the Contact page.
"""

PRIVACY = """This page explains what personal information we collect, why, who helps us process it, and the choices you have. It is written for visitors in Canada (PIPEDA and Canada's Anti-Spam Legislation) and the United States (including California's privacy laws).

## What we collect

- **Account:** e-mail address, password (stored only as a one-way hash), optional name, time zone, theme and notification choices.
- **What you save:** teams and players you follow, saved forecasts, notes and saved searches.
- **Plan and payment records:** plan, amounts, dates and status. Card details go straight to Stripe; we never see or store card numbers.
- **Sign-in history:** time, IP address and browser of sign-ins, kept for 90 days for security.
- **Usage:** anonymous page and feature counts. Our own analytics uses no cookies and does not store IP addresses.
- **Messages:** what you send through the Contact page.

We do not collect your location, device identifiers, date of birth or contacts.

## Why we use it

To run your account and the features you use, to bill paid plans, to keep the site secure, to send the e-mails you asked for, and to improve the site. We send marketing e-mail only if you opt in, and every one has a one-click unsubscribe link and our postal address.

## Who helps us (sub-processors)

- **Hosting provider:** runs the site.
- **MongoDB:** stores the database.
- **Stripe:** handles payments.
- **Resend (or the e-mail provider named in our settings):** sends e-mail.

Each only receives what it needs to do its job.

## Cookies and optional tools

The site needs one cookie to keep you signed in. Optional tools (such as advertising or measurement tags) load only if you choose "Allow optional" in the banner, and never when your browser sends Do Not Track or Global Privacy Control. You can change your choice at any time with the Privacy choices link in the footer.

## Selling or sharing

We do not sell personal information. If optional advertising tags are ever turned on, they run only with your consent, and you can withdraw it with the Privacy choices link.

## Your rights and choices

- **See or download your data:** Account > Privacy > Download my data.
- **Delete your account:** Account > Privacy > Delete account. This removes your account and what you saved. Payment records are kept, without your name or e-mail, where the law requires it.
- **Correct your data:** edit your profile, or ask us through the Contact page.
- **Stop marketing e-mail:** use the unsubscribe link, or switch it off in Account > Notifications.
- **California residents** can ask to know, delete or correct personal information, and to opt out of sale or sharing. We do not discriminate against anyone for using these rights.

## How long we keep it

Account data stays until you delete your account. Sign-in history is kept for 90 days. Payment records are kept as long as tax law requires.

## Age

The site is for adults (18+). We do not knowingly collect information from anyone under 18.

## Contact and complaints

The site owner is responsible for privacy. Reach us through the Contact page. In Canada you can also complain to the Office of the Privacy Commissioner of Canada.
"""

ABOUT = f"""We build football forecasts that show their working.

Every forecast on the site says how likely a player or team is to reach a stat line, how sure we are (the range), and why: form, minutes, the opponent, the referee and the lineup.

## How we keep it honest

- **We publish our record.** The Track Record page shows how often forecasts at each level were reached, misses included.
- **We show uncertainty.** A forecast comes with a range, and lines before confirmed lineups are labelled.
- **We say when data is old.** If our data feed falls behind, the site tells you.

The site is in beta: the forecast engine has been tested on past seasons and is now being scored on live matches.

{DISCLAIMER}

Questions or ideas? Use the Contact page.
"""

PAGES = {"terms": ("Terms of use", TERMS), "privacy": ("Privacy policy", PRIVACY), "about": ("About", ABOUT)}


def seed(db) -> list[str]:
    """Insert any missing legal page. Never overwrites a saved page. Returns the slugs inserted."""
    now = datetime.now(timezone.utc)
    added = []
    for slug, (title, body) in PAGES.items():
        r = db.content_pages.update_one({"slug": slug},
                                        {"$setOnInsert": {"slug": slug, "title": title, "body_md": body.strip() + "\n",
                                                          "published": True, "starter": True, "updated_at": now, "updated_by": "system"}},
                                        upsert=True)
        if r.upserted_id is not None:
            added.append(slug)
    return added


def needs_review(db) -> list[str]:
    """Legal slugs that are missing or still the unreviewed starter text."""
    have = {p["slug"]: p for p in db.content_pages.find({"slug": {"$in": list(LEGAL_SLUGS)}}, {"_id": 0, "slug": 1, "starter": 1})}
    return [s for s in LEGAL_SLUGS if s not in have or have[s].get("starter")]
