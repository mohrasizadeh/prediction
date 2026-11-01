"""Legal pages (docs/36 C2): Terms, Privacy and About exist from the first start, say what docs/03 and the launch
markets need, never overwrite an admin's page, and keep an admin alert open until each one has been reviewed."""
from testkit import *
import alerts as AL, legal_pages as L, textguard

with TestClient(srv.app) as owner:
    admin, support, analyst = boot(owner)
    anon = TestClient(srv.app)

    for slug in ("terms", "privacy", "about"):
        r = anon.get(f"/api/public/pages/{slug}")
        check(r.status_code == 200 and len(r.json()["body_md"]) > 300, f"/legal/{slug} has content from the first start")
    terms, privacy, about = (anon.get(f"/api/public/pages/{s}").json()["body_md"] for s in ("terms", "privacy", "about"))
    check("at least 18 years old" in terms, "Terms: adults only (18+)")
    check("renew automatically" in terms and "cancel" in terms.lower(), "Terms: automatic renewal and how to cancel are stated")
    check(L.DISCLAIMER in terms and L.DISCLAIMER in about, "Terms and About carry the exact disclaimer")
    check(all(w in privacy for w in ("Hosting provider", "MongoDB", "Stripe", "Resend")), "Privacy: names the sub-processors (docs/03 section 6)")
    check("California" in privacy and "Privacy Commissioner of Canada" in privacy and "do not sell" in privacy.lower(), "Privacy: covers California and Canada")
    check(textguard.find([t for _, t in L.PAGES.values()] + [h for h, _ in L.PAGES.values()]) == [], "no banned words (the disclaimer sentence is the only allowed use)")

    # the admin is told until every page is reviewed
    AL.evaluate(db)
    a = [x for x in AL.open_alerts(db) if x["key"] == "legal_pages"]
    check(a and "terms" in a[0]["text"] and "privacy" in a[0]["text"], "admin alert: legal pages still need review")
    pages = {p["slug"]: p for p in admin.get("/api/admin/content").json()["pages"]}
    check(pages["terms"].get("starter") is True, "the Pages list marks starter text")
    for slug in ("terms", "privacy", "about"):
        check(admin.put(f"/api/admin/content/{slug}", json={"title": slug.title(), "body_md": f"Reviewed {slug} text."}).status_code == 200, f"admin saves {slug}")
    check(not admin.get("/api/admin/content").json()["pages"][0].get("starter"), "saving clears the starter mark")
    AL.evaluate(db)
    check(not [x for x in AL.open_alerts(db) if x["key"] == "legal_pages"], "alert closes once all three are reviewed")

    # seeding again (next start) never overwrites a saved page, and a deleted page comes back as starter text
    db.content_pages.delete_one({"slug": "about"})
    added = L.seed(db)
    check(added == ["about"] and anon.get("/api/public/pages/terms").json()["body_md"] == "Reviewed terms text.", "restart: saved pages kept, missing page restored")
    check(L.needs_review(db) == ["about"], "...and only that one needs review again")

print("\nALL LEGAL CHECKS PASSED")
