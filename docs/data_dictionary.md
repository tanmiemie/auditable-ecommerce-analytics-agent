# Raw Data Dictionary

All timestamps are stored as ISO-8601 UTC strings unless a field explicitly says
otherwise. Raw tables intentionally contain defects; table grain describes the
intended source grain, not a guarantee that every raw row obeys it.

## `users`

Intended grain: one row per registered user.

- `user_id`: registered-user identifier.
- `signup_ts`: registration timestamp.
- `country`: US, CA, or GB.
- `acquisition_channel`: raw, non-canonical channel label.
- `platform`: first-seen platform.
- `is_employee`: known internal/test account flag.

## `identity_map`

Intended grain: one mapping version per anonymous identifier.

- `anonymous_id`, `user_id`
- `effective_from`, `loaded_at`
- `match_status`: matched, pending, or ambiguous.

## `sessions`

Intended grain: one row per analytics session.

- `session_id`, `anonymous_id`, `user_id`
- `session_start`, `ingested_at`
- `platform`, `app_version`, `channel_raw`, `campaign_id`
- `user_agent`, `ip_hash`
- `is_known_bot`: populated only for bots known to the source system.
- `sessionization_version`: source rule used to create the session.

## `events`

Intended grain: one row per emitted client event. Network retries may violate
uniqueness.

- `event_id`, `session_id`, `anonymous_id`, `user_id`
- `event_ts`, `ingested_at`
- `event_name_raw`
- `platform`, `app_version`, `product_id`
- `quantity_raw`, `cart_value_raw`, `experiment_id`
- `source_event_id`: original event identifier for retry duplicates.

## `products`

Intended grain: one row per product.

- `product_id`, `category`, `brand`, `list_price_usd`, `cost_usd`
- `inventory_status`

## `orders`

Intended grain: one row per server-side order.

- `order_id`, `user_id`, `anonymous_id`, `session_id`
- `order_ts`, `ingested_at`
- `subtotal`, `discount`, `shipping_fee`, `tax`, `order_total`
- `currency`, `payment_status`, `shipping_country`
- `coupon_code`, `device_id`, `payment_token_hash`
- `is_confirmed_fraud`: delayed ground-truth label available to risk systems.

## `order_status_history`

Intended grain: one row per order status transition. This is not an order-level
table and must not be summed as revenue without deduplication.

## `refunds`

Intended grain: one row per refund request.

- `requested_at`, `completed_at`, and `ingested_at` may differ materially.

## `experiment_assignments` and `experiment_exposures`

Assignments represent randomization; exposures represent actual feature views.
They are deliberately not interchangeable.

## `app_releases` and `campaigns`

Calendars provided to the agent as potential explanatory context. Temporal
coincidence is evidence for investigation, not proof of causality.

