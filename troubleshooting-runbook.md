# Stripe Integration Troubleshooting Runbook

This runbook is for debugging issues in the Flask + Stripe Checkout integration.

The goal is to diagnose problems systematically instead of guessing.

---

# Quick System Overview

## Main flow

```text
User clicks Buy
→ Flask creates local pending order
→ Flask creates Stripe Checkout Session
→ Flask stores stripe_session_id
→ User pays on Stripe Checkout
→ Stripe sends checkout.session.completed webhook
→ Flask verifies webhook signature
→ Flask logs event
→ Flask marks order paid
→ Flask stores stripe_payment_intent_id
```

## Important local pages

```text
/orders
```

Shows local orders.

```text
/events
```

Shows received Stripe webhook events.

```text
/debug/session/<stripe_session_id>
```

Retrieves a Checkout Session from Stripe and displays related PaymentIntent data.

```text
/debug/payment-intents
```

Lists recent PaymentIntents from Stripe.

---

# Issue 1 — Payment succeeds but order remains pending

## Symptom

Stripe shows a successful payment, but `/orders` shows:

```text
status = pending
```

## First checks

1. Confirm the payment succeeded in Stripe Dashboard.
2. Check `/events` for:

```text
checkout.session.completed
```

3. Check whether the event has:

```text
processed = Yes
```

4. Check whether the order has:

```text
stripe_session_id
stripe_payment_intent_id
```

## Terminal checks

In Stripe CLI terminal, look for:

```text
checkout.session.completed
```

and response status:

```text
[200]
[400]
[403]
[500]
```

In Flask terminal, look for:

```text
POST /webhook
```

## Likely causes

- Stripe CLI listener is not running.
- Listener is forwarding to the wrong URL.
- Webhook secret is outdated.
- Flask was not restarted after `.env` changed.
- Signature verification failed.
- Webhook route crashed with `500`.
- Event was logged but not processed.
- Local order could not be matched by `stripe_session_id`.

## Fixes

### If Flask shows no `POST /webhook`

Restart listener with explicit IP:

```bash
./stripe listen --forward-to 127.0.0.1:5000/webhook
```

### If webhook returns `400 Invalid signature`

Update `.env`:

```bash
STRIPE_WEBHOOK_SECRET=whsec_current_value
```

Then restart Flask:

```bash
CTRL + C
python app.py
```

### If webhook returns `500`

Check Flask traceback.

Common bug:

```python
session.get("payment_intent")
```

Fix:

```python
session.payment_intent
```

### If event shows `processed = No` and `error = None`

Check duplicate event logic.

`event_already_processed()` should check:

```sql
processed = 1
```

not only whether the event exists.

---

# Issue 2 — Webhook signature verification fails

## Symptom

Flask returns:

```text
400 Invalid signature
```

## Likely causes

- Wrong `STRIPE_WEBHOOK_SECRET`.
- Stripe CLI listener was restarted and generated a new `whsec_...`.
- `.env` was updated but Flask was not restarted.
- The webhook route is not using the raw request body.
- The JSON payload was parsed before verification.

## Checks

Confirm webhook route uses:

```python
payload = request.data
sig_header = request.headers.get("Stripe-Signature")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
```

and:

```python
stripe.Webhook.construct_event(
    payload,
    sig_header,
    endpoint_secret
)
```

## Fix

1. Copy current `whsec_...` from Stripe CLI.
2. Update `.env`.
3. Restart Flask.

```bash
CTRL + C
python app.py
```

## Prevention

- Always restart Flask after `.env` changes.
- Do not parse JSON before signature verification.
- Keep `STRIPE_WEBHOOK_SECRET` separate from `STRIPE_SECRET_KEY`.

---

# Issue 3 — Stripe CLI shows events but Flask shows no webhook logs

## Symptom

Stripe CLI shows events like:

```text
checkout.session.completed
```

but Flask terminal does not show:

```text
POST /webhook
```

## Likely cause

The webhook request is not reaching Flask.

## Checks

Confirm Flask is running:

```text
Running on http://127.0.0.1:5000
```

Test Flask manually:

```bash
curl -i http://127.0.0.1:5000/events
```

Expected:

```text
HTTP/1.1 200 OK
```

## Fix

Use:

```bash
./stripe listen --forward-to 127.0.0.1:5000/webhook
```

instead of:

```bash
./stripe listen --forward-to localhost:5000/webhook
```

---

# Issue 4 — Browser shows 403 but Flask works

## Symptom

Browser shows:

```text
Access to 127.0.0.1 was denied
HTTP ERROR 403
```

but terminal shows:

```bash
curl -i http://127.0.0.1:5000/events
```

returns:

```text
HTTP/1.1 200 OK
```

## Likely cause

Browser-specific cache, redirect, or security state issue.

## Fix

Try:

```text
http://127.0.0.1:5000/events
```

in an incognito/private window.

If that works, clear site data for:

```text
127.0.0.1
localhost
```

---

# Issue 5 — Duplicate webhook event received

## Symptom

The same Stripe event is received again.

Example:

```text
evt_...
```

already exists in `/events`.

## Expected behavior

The app should skip it safely:

```text
Skipping already processed event: evt_...
```

and return:

```text
200
```

## Checks

In `/events`, confirm:

```text
processed = Yes
```

For duplicate testing:

```bash
./stripe events resend evt_...
```

## Fix

Make sure duplicate check uses:

```python
if event_already_processed(stripe_event_id):
    return "Already processed", 200
```

and that `event_already_processed()` checks:

```sql
WHERE stripe_event_id = ? AND processed = 1
```

## Prevention

- Store Stripe event IDs.
- Make `stripe_event_id` unique.
- Mark processed only after business logic succeeds.
- Return `200` when safely skipping duplicates.

---

# Issue 6 — Metadata missing

## Symptom

Checkout Session metadata exists, but PaymentIntent metadata is missing.

## Why it matters

PaymentIntent events may not contain enough local context to identify the internal order.

## Checks

Open:

```text
/debug/session/<stripe_session_id>
```

Confirm metadata appears on both:

```text
Checkout Session
PaymentIntent
```

## Fix

When creating the Checkout Session, include:

```python
metadata={
    "order_id": str(order_id),
    "integration_source": "stripe_ic_lab"
},
payment_intent_data={
    "metadata": {
        "order_id": str(order_id),
        "product_name": "Baby Cardigan",
        "integration_source": "stripe_ic_lab"
    }
}
```

---

# Issue 7 — Checkout Session creation fails

## Symptom

Clicking Buy does not redirect to Stripe Checkout.

## Likely causes

- Missing `STRIPE_SECRET_KEY`.
- Missing `STRIPE_PRICE_ID`.
- Wrong Price ID.
- Test mode key used with live mode Price ID, or vice versa.
- Stripe API error.

## Checks

Check `.env`:

```bash
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PRICE_ID=price_...
```

Check code:

```python
price_id = os.getenv("STRIPE_PRICE_ID")

if not price_id:
    return "Price ID not set in environment variables", 500
```

Check Flask terminal traceback.

## Fix

- Use the correct Price ID.
- Use matching test mode secret key and test mode Price ID.
- Restart Flask after `.env` changes.

---

# Issue 8 — Debug session page fails

## Symptom

Opening:

```text
/debug/session/cs_test_...
```

returns an error.

## Possible causes

- Invalid Checkout Session ID.
- Session belongs to different Stripe account or mode.
- Secret key is wrong.
- Stripe object access issue.
- Metadata object is not a normal Python dictionary.

## Checks

Confirm session ID starts with:

```text
cs_test_
```

Check Flask traceback.

If metadata iteration fails, avoid assuming Stripe metadata supports normal dictionary methods.

## Fix

Extract the specific metadata fields needed:

```python
def extract_metadata(metadata):
    if not metadata:
        return {}

    keys = [
        "order_id",
        "product_name",
        "integration_source"
    ]

    extracted = {}

    for key in keys:
        try:
            value = metadata[key]
        except Exception:
            value = getattr(metadata, key, None)

        if value:
            extracted[key] = value

    return extracted
```

---

# Issue 9 — PaymentIntent listing fails

## Symptom

Opening:

```text
/debug/payment-intents
```

returns an error.

## Likely causes

- Missing or invalid `STRIPE_SECRET_KEY`.
- Stripe API issue.
- Incorrect code in list route.

## Checks

Confirm route uses:

```python
stripe.PaymentIntent.list(limit=10)
```

For next page:

```python
stripe.PaymentIntent.list(
    limit=10,
    starting_after="pi_..."
)
```

## Pagination notes

Stripe uses cursor-based pagination.

Use:

```text
starting_after
```

not:

```text
page=2
```

---

# General Debugging Checklist

When something fails, check in this order:

1. Browser page
2. Flask terminal
3. Stripe CLI terminal
4. `/orders`
5. `/events`
6. Stripe Dashboard
7. `.env`
8. Git status if code changed

---

# Local Development Commands

## Start Flask

```bash
cd ~/Documents/stripe_project
source .venv/bin/activate
python app.py
```

## Start Stripe CLI listener

```bash
./stripe listen --forward-to 127.0.0.1:5000/webhook
```

## Resend a Stripe event

```bash
./stripe events resend evt_...
```

## Check Git status

```bash
git status
```

---

# Escalation Notes

If this were a real customer implementation, I would collect:

- Stripe request ID if available
- Stripe event ID
- Checkout Session ID
- PaymentIntent ID
- local order ID
- webhook response status
- timestamp
- relevant application logs

This allows support, engineering, or Stripe teams to investigate efficiently.
