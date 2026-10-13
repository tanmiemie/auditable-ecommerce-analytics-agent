#!/usr/bin/env python3
"""Generate reproducible, intentionally messy ecommerce analytics data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
GT_DIR = ROOT / "ground_truth"
START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_hash(value: str, size: int = 12) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:size]


def choice_weighted(rng, pairs):
    values, weights = zip(*pairs)
    return rng.choices(values, weights=weights, k=1)[0]


def write_csv(name, rows):
    path = RAW_DIR / f"{name}.csv"
    if not rows:
        raise ValueError(f"No rows generated for {name}")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def load_sqlite(table_rows):
    db_path = ROOT / "data" / "ecommerce_raw.sqlite"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        for name, rows in table_rows.items():
            columns = list(rows[0].keys())
            defs = ", ".join(f'"{c}" TEXT' for c in columns)
            conn.execute(f'DROP TABLE IF EXISTS "{name}"')
            conn.execute(f'CREATE TABLE "{name}" ({defs})')
            marks = ",".join("?" for _ in columns)
            conn.executemany(
                f'INSERT INTO "{name}" VALUES ({marks})',
                ([row[c] for c in columns] for row in rows),
            )
            conn.execute(f'CREATE INDEX IF NOT EXISTS "idx_{name}_date" ON "{name}" ("{columns[0]}")')
        conn.commit()
    finally:
        conn.close()
    return db_path


def generate(seed: int, n_users: int, n_days: int):
    rng = random.Random(seed)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    GT_DIR.mkdir(parents=True, exist_ok=True)

    incident_manifest = [
        {
            "id": "BOT-01", "class": "automation_or_security", "name": "scraper_traffic",
            "start": "2026-01-10", "end": "2026-01-12", "affected": "web / selected electronics products",
            "expected_signals": ["visits spike", "very high views per session", "near-zero conversion", "regular timing"],
            "expected_conclusion": "suspected bot traffic; security confirmation required",
        },
        {
            "id": "VIS-01", "class": "data_quality", "name": "duplicate_sdk_events",
            "start": "2026-02-05", "end": "2026-02-08", "affected": "android 5.4.0",
            "expected_signals": ["duplicate event_id", "source_event_id repeats", "event count rises without user growth"],
            "expected_conclusion": "client retry duplication; deduplicate before metric use",
        },
        {
            "id": "VIS-02", "class": "data_quality", "name": "sessionization_timeout_change",
            "start": "2026-02-15", "end": "2026-02-18", "affected": "web",
            "expected_signals": ["sessions per user rises", "events per session falls", "orders stable"],
            "expected_conclusion": "visit inflation caused by sessionization configuration",
        },
        {
            "id": "FRAUD-01", "class": "automation_or_security", "name": "payment_velocity_attack",
            "start": "2026-02-25", "end": "2026-02-26", "affected": "new accounts / web",
            "expected_signals": ["many accounts share devices", "payment token reuse", "small tests followed by larger orders"],
            "expected_conclusion": "suspected coordinated fraud; route to risk review",
        },
        {
            "id": "TRK-01", "class": "data_quality", "name": "ios_checkout_event_missing",
            "start": "2026-03-15", "end": "2026-03-18", "affected": "ios 6.1.0",
            "expected_signals": ["client checkout event collapses", "server orders remain", "other platforms unaffected"],
            "expected_conclusion": "iOS tracking outage; do not use client checkout rate",
        },
        {
            "id": "TRK-02", "class": "data_quality", "name": "android_event_rename",
            "start": "2026-03-25", "end": "2026-04-30", "affected": "android 6.2.0",
            "expected_signals": ["add_to_cart falls", "cart_add appears", "total canonical cart actions remain plausible"],
            "expected_conclusion": "schema migration; canonicalize both event names by version/date",
        },
        {
            "id": "FRAUD-02", "class": "automation_or_security", "name": "promotion_abuse",
            "start": "2026-04-02", "end": "2026-04-07", "affected": "WELCOME20 coupon",
            "expected_signals": ["shared devices across accounts", "orders cluster near coupon threshold", "low margin"],
            "expected_conclusion": "suspected promotion abuse; quantify and route to risk review",
        },
        {
            "id": "TRK-03", "class": "data_quality", "name": "experiment_property_missing",
            "start": "2026-04-10", "end": "2026-04-13", "affected": "ios 6.2.1",
            "expected_signals": ["event volume stable", "experiment_id null rate spikes", "iOS isolated"],
            "expected_conclusion": "experiment attribution is incomplete; experiment result requires repair",
        },
    ]
    business_manifest = [
        {"id": "BIZ-01", "name": "paid_social_campaign", "start": "2026-01-20", "end": "2026-01-26", "truth": "legitimate campaign traffic growth"},
        {"id": "BIZ-02", "name": "spring_promotion", "start": "2026-03-05", "end": "2026-03-10", "truth": "legitimate promotion-driven order growth"},
        {"id": "BIZ-03", "name": "popular_product_stockout", "start": "2026-04-15", "end": "2026-04-18", "truth": "real conversion decline due to inventory"},
        {"id": "BIZ-04", "name": "android_ux_regression", "start": "2026-04-21", "end": "2026-04-24", "truth": "real behavioral decline, not missing telemetry"},
    ]

    products = []
    categories = ["electronics", "home", "beauty", "apparel", "fitness"]
    for i in range(1, 301):
        category = categories[(i - 1) % len(categories)]
        price = round(rng.uniform(12, 240), 2)
        products.append({
            "product_id": f"P{i:04d}", "category": category,
            "brand": f"Brand{1 + i % 18:02d}", "list_price_usd": f"{price:.2f}",
            "cost_usd": f"{price * rng.uniform(.35, .68):.2f}",
            "inventory_status": "in_stock",
        })

    channels = [
        ("organic", 32), ("paid_search", 18), ("paid_social", 13),
        ("email", 12), ("affiliate", 8), ("referral", 7), ("direct", 10),
    ]
    platforms = [("ios", 38), ("android", 37), ("web", 25)]
    users, identity_map = [], []
    for i in range(1, n_users + 1):
        uid = f"U{i:06d}"
        platform = choice_weighted(rng, platforms)
        signup = START + timedelta(days=rng.randrange(max(1, n_days)), seconds=rng.randrange(86400))
        channel = choice_weighted(rng, channels)
        raw_channel = channel
        if channel == "paid_social" and rng.random() < .22:
            raw_channel = rng.choice(["Paid Social", "facebook", "fb_ads", "meta"])
        users.append({
            "user_id": uid, "signup_ts": iso(signup),
            "country": choice_weighted(rng, [("US", 78), ("CA", 13), ("GB", 9)]),
            "acquisition_channel": raw_channel, "platform": platform,
            "is_employee": "1" if i <= max(5, n_users // 1000) else "0",
        })
        anonymous = f"A{stable_hash(uid)}"
        loaded = signup + timedelta(hours=rng.randint(0, 36))
        identity_map.append({
            "anonymous_id": anonymous, "user_id": uid,
            "effective_from": iso(signup), "loaded_at": iso(loaded),
            "match_status": "pending" if rng.random() < .025 else "matched",
        })

    releases = [
        {"platform": "ios", "app_version": "6.1.0", "released_at": "2026-03-15T08:00:00Z", "release_note": "checkout UI refresh"},
        {"platform": "android", "app_version": "6.2.0", "released_at": "2026-03-25T08:00:00Z", "release_note": "cart instrumentation migration"},
        {"platform": "ios", "app_version": "6.2.1", "released_at": "2026-04-10T08:00:00Z", "release_note": "experiment SDK update"},
        {"platform": "android", "app_version": "6.3.0", "released_at": "2026-04-21T08:00:00Z", "release_note": "product page redesign"},
    ]
    campaigns = [
        {"campaign_id": "CAMP_SOCIAL_JAN", "channel": "paid_social", "start_date": "2026-01-20", "end_date": "2026-01-26", "daily_spend": "8500", "campaign_type": "acquisition"},
        {"campaign_id": "CAMP_SPRING", "channel": "email", "start_date": "2026-03-05", "end_date": "2026-03-10", "daily_spend": "2100", "campaign_type": "promotion"},
    ]

    sessions, events, orders, order_history, refunds = [], [], [], [], []
    assignments, exposures = [], []
    session_counter = event_counter = order_counter = 0
    user_by_id = {u["user_id"]: u for u in users}
    anon_by_user = {r["user_id"]: r["anonymous_id"] for r in identity_map}

    def app_version(platform, day):
        if platform == "ios":
            if day >= 99: return "6.2.1"
            if day >= 73: return "6.1.0"
            return "5.9.0"
        if platform == "android":
            if day >= 110: return "6.3.0"
            if day >= 83: return "6.2.0"
            if 35 <= day <= 38: return "5.4.0"
            return "5.3.0"
        return "web-2026.1"

    def add_event(session, name, when, product_id="", quantity="", cart_value="", experiment_id=""):
        nonlocal event_counter
        event_counter += 1
        eid = f"E{event_counter:09d}"
        lag_hours = rng.choices([1, 6, 24, 48], weights=[88, 7, 3, 2])[0]
        row = {
            "event_id": eid, "session_id": session["session_id"],
            "anonymous_id": session["anonymous_id"], "user_id": session["user_id"],
            "event_ts": iso(when), "ingested_at": iso(when + timedelta(hours=lag_hours)),
            "event_name_raw": name, "platform": session["platform"],
            "app_version": session["app_version"], "product_id": product_id,
            "quantity_raw": quantity, "cart_value_raw": cart_value,
            "experiment_id": experiment_id, "source_event_id": eid,
        }
        events.append(row)
        return row

    for day in range(n_days):
        date = START + timedelta(days=day)
        campaign_boost = 2.2 if 19 <= day <= 25 else 1.0
        promo_boost = 1.55 if 63 <= day <= 68 else 1.0
        daily_sessions = int((n_users * .055) * campaign_boost)
        for _ in range(daily_sessions):
            uid = f"U{rng.randint(1, n_users):06d}"
            user = user_by_id[uid]
            platform = user["platform"] if rng.random() < .83 else choice_weighted(rng, platforms)
            channel = user["acquisition_channel"]
            campaign_id = ""
            if 19 <= day <= 25 and rng.random() < .58:
                channel, campaign_id = "Paid Social", "CAMP_SOCIAL_JAN"
            elif 63 <= day <= 68 and rng.random() < .45:
                channel, campaign_id = "email", "CAMP_SPRING"
            session_counter += 1
            start = date + timedelta(seconds=rng.randrange(86400))
            session = {
                "session_id": f"S{session_counter:08d}", "anonymous_id": anon_by_user[uid],
                "user_id": uid, "session_start": iso(start),
                "ingested_at": iso(start + timedelta(hours=rng.choices([1, 12, 36], [94, 4, 2])[0])),
                "platform": platform, "app_version": app_version(platform, day),
                "channel_raw": channel, "campaign_id": campaign_id,
                "user_agent": f"ShopApp/{app_version(platform, day)}" if platform != "web" else "Mozilla/5.0",
                "ip_hash": stable_hash(f"{uid}-{day // 7}"), "is_known_bot": "0",
                "sessionization_version": "v2_5min" if platform == "web" and 45 <= day <= 48 else "v1_30min",
            }
            sessions.append(session)
            product = rng.choice(products)
            t = start
            add_event(session, "app_open" if platform != "web" else "page_view", t)
            views = rng.randint(1, 5)
            for _view in range(views):
                t += timedelta(seconds=rng.randint(8, 95))
                ev = add_event(session, "view_item", t, product["product_id"])
                # VIS-01: raw SDK retry duplicates on Android 5.4.0.
                if platform == "android" and session["app_version"] == "5.4.0" and rng.random() < .38:
                    duplicate = dict(ev)
                    duplicate["ingested_at"] = iso(t + timedelta(hours=2))
                    events.append(duplicate)

            add_prob = .24
            # BIZ-04 is a real UX regression: telemetry remains present, behavior changes.
            if platform == "android" and 110 <= day <= 113:
                add_prob *= .55
            # BIZ-03 stockout reduces actions on electronics.
            if 104 <= day <= 107 and product["category"] == "electronics":
                add_prob *= .28
            did_add = rng.random() < add_prob
            if did_add:
                t += timedelta(seconds=rng.randint(10, 140))
                event_name = "cart_add" if platform == "android" and day >= 83 else "add_to_cart"
                quantity = str(rng.choice([1, 1, 1, 2]))
                if platform == "android" and day >= 83 and rng.random() < .04:
                    quantity = "two"
                exp_prop = "EXP_RECS_01"
                if platform == "ios" and 99 <= day <= 102:
                    exp_prop = ""
                add_event(session, event_name, t, product["product_id"], quantity, product["list_price_usd"], exp_prop)

            checkout_prob = .47 if did_add else .015
            did_checkout = rng.random() < checkout_prob
            if did_checkout:
                t += timedelta(seconds=rng.randint(15, 220))
                # TRK-01: server behavior continues while client event disappears.
                if not (platform == "ios" and 73 <= day <= 76):
                    add_event(session, "begin_checkout", t, product["product_id"], "1", product["list_price_usd"])

            purchase_prob = (.62 if did_checkout else .002) * promo_boost
            if platform == "android" and 110 <= day <= 113:
                purchase_prob *= .72
            if rng.random() < min(.88, purchase_prob):
                t += timedelta(seconds=rng.randint(20, 300))
                order_counter += 1
                oid = f"O{order_counter:07d}"
                price = float(product["list_price_usd"])
                discount = price * (.20 if 63 <= day <= 68 else 0)
                total = price - discount + 4.99
                add_event(session, "purchase", t, product["product_id"], "1", f"{total:.2f}")
                order = {
                    "order_id": oid, "user_id": uid, "anonymous_id": session["anonymous_id"],
                    "session_id": session["session_id"], "order_ts": iso(t),
                    "ingested_at": iso(t + timedelta(minutes=rng.randint(2, 90))),
                    "subtotal": f"{price:.2f}", "discount": f"{discount:.2f}",
                    "shipping_fee": "4.99", "tax": f"{(price-discount)*.0825:.2f}",
                    "order_total": f"{total + (price-discount)*.0825:.2f}", "currency": "USD",
                    "payment_status": "paid", "shipping_country": user["country"],
                    "coupon_code": "SPRING20" if discount else "",
                    "device_id": stable_hash(session["anonymous_id"]),
                    "payment_token_hash": stable_hash(f"pay-{uid}"), "is_confirmed_fraud": "0",
                }
                orders.append(order)
                for status, minutes in [("placed", 0), ("paid", 2), ("shipped", 24 * 60), ("completed", 72 * 60)]:
                    order_history.append({
                        "order_id": oid, "status": status,
                        "status_ts": iso(t + timedelta(minutes=minutes)),
                        "ingested_at": iso(t + timedelta(minutes=minutes + rng.randint(1, 30))),
                        "order_total_snapshot": order["order_total"],
                    })
                if rng.random() < .035:
                    request = t + timedelta(days=rng.randint(2, 9))
                    completed = request + timedelta(days=rng.randint(1, 6))
                    refunds.append({
                        "refund_id": f"R{len(refunds)+1:06d}", "order_id": oid,
                        "refund_amount": order["order_total"], "requested_at": iso(request),
                        "completed_at": iso(completed), "ingested_at": iso(completed + timedelta(hours=rng.randint(2, 48))),
                        "reason": rng.choice(["changed_mind", "damaged", "late_delivery"]),
                    })

            # VIS-02: split one web visit into an extra session without new behavior.
            if platform == "web" and 45 <= day <= 48 and rng.random() < .42:
                session_counter += 1
                split = dict(session)
                split["session_id"] = f"S{session_counter:08d}"
                split["session_start"] = iso(start + timedelta(minutes=7))
                split["sessionization_version"] = "v2_5min"
                sessions.append(split)

        # BOT-01 adds highly regular scraper sessions independent of real users.
        if 9 <= day <= 11:
            for b in range(max(75, n_users // 80)):
                session_counter += 1
                start = date + timedelta(seconds=b * 300 % 86400)
                bot_session = {
                    "session_id": f"S{session_counter:08d}", "anonymous_id": f"BOT{day:03d}{b:05d}",
                    "user_id": "", "session_start": iso(start), "ingested_at": iso(start + timedelta(minutes=3)),
                    "platform": "web", "app_version": "web-2026.1", "channel_raw": "direct", "campaign_id": "",
                    "user_agent": "Mozilla/5.0 PriceMonitor", "ip_hash": stable_hash(f"bot-{b % 8}"),
                    "is_known_bot": "0", "sessionization_version": "v1_30min",
                }
                sessions.append(bot_session)
                for j in range(18):
                    product = products[(b * 7 + j) % 60]
                    add_event(bot_session, "view_item", start + timedelta(seconds=j * 5), product["product_id"])

    # FRAUD-01 velocity attack: many accounts/devices reuse a payment token.
    for i in range(max(35, n_users // 250)):
        user_num = n_users - i
        uid = f"U{user_num:06d}"
        day = 55 + i % 2
        when = START + timedelta(days=day, hours=2, minutes=i)
        session_counter += 1
        sid = f"S{session_counter:08d}"
        session = {
            "session_id": sid, "anonymous_id": anon_by_user[uid], "user_id": uid,
            "session_start": iso(when), "ingested_at": iso(when + timedelta(minutes=3)),
            "platform": "web", "app_version": "web-2026.1", "channel_raw": "direct", "campaign_id": "",
            "user_agent": "Mozilla/5.0", "ip_hash": stable_hash(f"velocity-{i % 3}"),
            "is_known_bot": "0", "sessionization_version": "v1_30min",
        }
        sessions.append(session)
        order_counter += 1
        amount = 5.00 if i < 12 else 180.00 + (i % 5) * 20
        oid = f"O{order_counter:07d}"
        orders.append({
            "order_id": oid, "user_id": uid, "anonymous_id": anon_by_user[uid], "session_id": sid,
            "order_ts": iso(when), "ingested_at": iso(when + timedelta(minutes=2)),
            "subtotal": f"{amount:.2f}", "discount": "0.00", "shipping_fee": "0.00", "tax": "0.00",
            "order_total": f"{amount:.2f}", "currency": "USD", "payment_status": "paid",
            "shipping_country": "US", "coupon_code": "", "device_id": f"FRAUD_DEVICE_{i%4}",
            "payment_token_hash": "SHARED_TOKEN_VELOCITY", "is_confirmed_fraud": "1",
        })

    # FRAUD-02 promotion abuse: shared device/address-like signals with WELCOME20.
    for i in range(max(45, n_users // 220)):
        uid = f"U{n_users - 100 - i:06d}"
        when = START + timedelta(days=91 + i % 6, hours=10, minutes=i)
        order_counter += 1
        amount = 50 + (i % 3)
        orders.append({
            "order_id": f"O{order_counter:07d}", "user_id": uid, "anonymous_id": anon_by_user[uid], "session_id": "",
            "order_ts": iso(when), "ingested_at": iso(when + timedelta(minutes=3)),
            "subtotal": f"{amount:.2f}", "discount": "10.00", "shipping_fee": "0.00", "tax": "3.30",
            "order_total": f"{amount-6.70:.2f}", "currency": "USD", "payment_status": "paid",
            "shipping_country": "US", "coupon_code": "WELCOME20", "device_id": f"PROMO_DEVICE_{i%5}",
            "payment_token_hash": f"PROMO_PAY_{i%7}", "is_confirmed_fraud": "1",
        })

    # A small experiment dataset with imperfect exposure coverage.
    for i in range(1, min(n_users, 5000) + 1):
        uid = f"U{i:06d}"
        variant = "treatment" if i % 2 else "control"
        assigned = START + timedelta(days=80, seconds=i)
        assignments.append({"experiment_id": "EXP_RECS_01", "user_id": uid, "variant": variant, "assigned_at": iso(assigned)})
        if i % 9 != 0:
            exposures.append({"experiment_id": "EXP_RECS_01", "user_id": uid, "variant": variant, "exposed_at": iso(assigned + timedelta(hours=i % 48))})
    # A few malformed exposure records for integrity testing.
    for i in range(10):
        exposures.append({"experiment_id": "EXP_RECS_01", "user_id": f"UNASSIGNED_{i}", "variant": "treatment", "exposed_at": iso(START + timedelta(days=82, minutes=i))})

    table_rows = {
        "users": users, "identity_map": identity_map, "products": products,
        "sessions": sessions, "events": events, "orders": orders,
        "order_status_history": order_history, "refunds": refunds,
        "experiment_assignments": assignments, "experiment_exposures": exposures,
        "app_releases": releases, "campaigns": campaigns,
    }
    for name, rows in table_rows.items():
        write_csv(name, rows)
    db_path = load_sqlite(table_rows)

    manifest = {
        "dataset": "synthetic_ecommerce_v1", "seed": seed,
        "period": {"start": START.strftime("%Y-%m-%d"), "days": n_days},
        "incidents": incident_manifest, "legitimate_business_changes": business_manifest,
        "access_policy": "evaluator_only_do_not_expose_to_agent",
    }
    (GT_DIR / "incident_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    summary = {"seed": seed, "users_requested": n_users, "days": n_days, "database": str(db_path), "row_counts": {k: len(v) for k, v in table_rows.items()}}
    (GT_DIR / "generation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--users", type=int, default=10_000)
    parser.add_argument("--days", type=int, default=120)
    args = parser.parse_args()
    if args.days < 115:
        raise SystemExit("--days must be at least 115 so every v1 scenario is represented")
    if args.users < 1000:
        raise SystemExit("--users must be at least 1000")
    generate(args.seed, args.users, args.days)


if __name__ == "__main__":
    main()

