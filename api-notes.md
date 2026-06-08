# Stripe API Notes

This file documents the Stripe API concepts used in this project.

The purpose is to practice reading API documentation, identifying request requirements, understanding response objects, and explaining how Stripe objects relate to my local application.

---

# 1. Checkout Session Creation

## Business goal

Create a Stripe-hosted payment page so a customer can buy a product.

In this project, the product is:

```text
Baby Cardigan
```

## Direction of request

```text
My Flask app → Stripe API
```

This is an outbound API request from my backend to Stripe.

## Code location

```text
app.py
home()
```

## Stripe object created

```text
Checkout Session
```

## Code pattern

```python
checkout_session = stripe.checkout.Session.create(
    line_items=[
        {
            "price": price_id,
            "quantity": 1
        }
    ],
    mode="payment",
    success_url=url_for("success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
    cancel_url=url_for("cancel", _external=True),
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
)
```

## Important parameters

### `line_items`

Defines what the customer is buying.

This project uses an existing Stripe Price ID:

```python
"price": price_id
```

### `mode`

This project uses:

```python
mode="payment"
```

This means it is a one-time payment.

### `success_url`

Where Stripe redirects the customer after successful Checkout.

Important: this is useful for user experience, but it is not the reliable fulfillment trigger.

### `cancel_url`

Where Stripe redirects the customer if they cancel Checkout.

### `metadata`

Stores internal information on the Checkout Session.

In this project:

```text
order_id
integration_source
```

### `payment_intent_data.metadata`

Stores internal information on the underlying PaymentIntent.

In this project:

```text
order_id
product_name
integration_source
```

## Local database behavior

Before creating the Checkout Session, the app creates a local order:

```text
status = pending
```

After Stripe creates the Checkout Session, the app stores:

```text
stripe_session_id
```

on the local order.

## Why this matters

The local order gives my application its own source of truth.

The Checkout Session gives Stripe a hosted payment flow.

The `stripe_session_id` connects the local order to the Stripe Checkout Session.

---

# 2. Success Page Session Retrieval

## Business goal

Show a success page after the customer returns from Stripe Checkout.

## Direction of request

```text
My Flask app → Stripe API
```

## Code location

```text
app.py
success()
```

## Code pattern

```python
session_id = request.args.get("session_id")

session = stripe.checkout.Session.retrieve(session_id)

if session.payment_status == "paid":
    return render_template("success.html")
else:
    return redirect(url_for("cancel"))
```

## Important concept

The success page is not the reliable source of truth for fulfillment.

A customer may pay successfully but never return to the success page.

Possible reasons:

- browser closes
- internet connection drops
- redirect fails
- customer navigates away

## Correct fulfillment source

The webhook should update the local order from:

```text
pending → paid
```

The success page should mainly be used for customer experience.

---

# 3. Webhook Verification

## Business goal

Receive Stripe events securely and update local state.

## Direction of request

```text
Stripe → My Flask app
```

This is an inbound HTTP POST request from Stripe to my app.

## Code location

```text
app.py
stripe_webhook()
```

## Webhook route

```text
POST /webhook
```

## Code pattern

```python
payload = request.data
sig_header = request.headers.get("Stripe-Signature")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

event = stripe.Webhook.construct_event(
    payload,
    sig_header,
    endpoint_secret
)
```

## Important fields

### `request.data`

The raw request body.

This matters because Stripe signature verification depends on the exact raw payload.

### `Stripe-Signature`

Header sent by Stripe.

Used to verify that the event came from Stripe and was not tampered with.

### `STRIPE_WEBHOOK_SECRET`

The local webhook signing secret.

For Stripe CLI testing, this starts with:

```text
whsec_...
```

## Common failure

If the Stripe CLI listener is restarted, it may print a new `whsec_...`.

When that happens:

1. Update `.env`
2. Restart Flask

## Why this matters

Webhook endpoints are publicly reachable.

Signature verification protects the app from fake, spoofed, or modified webhook requests.

---

# 4. Webhook Event Used for Fulfillment

## Event

```text
checkout.session.completed
```

## Meaning

The customer completed the Stripe Checkout flow.

## Project behavior

When this event is received and verified, the app:

1. Extracts the Checkout Session ID.
2. Extracts the PaymentIntent ID.
3. Finds the local order by `stripe_session_id`.
4. Updates the order to `paid`.
5. Stores the PaymentIntent ID.
6. Marks the event as processed.

## Code pattern

```python
if event_type == "checkout.session.completed":
    session = event_object

    stripe_session_id = session.id
    stripe_payment_intent_id = session.payment_intent

    mark_order_paid_by_session(stripe_session_id)

    if stripe_payment_intent_id:
        update_payment_intent_by_session(
            stripe_session_id,
            stripe_payment_intent_id
        )
```

## Why this matters

The webhook is the reliable fulfillment trigger.

The success page is not enough.

---

# 5. Event Logging

## Business goal

Record webhook events for troubleshooting, visibility, and duplicate protection.

## Local table

```text
stripe_events
```

## Fields stored

```text
stripe_event_id
event_type
object_id
processed
error
created_at
```

## Why log events?

Event logging helps answer:

- Did Stripe send the event?
- Did my app receive the event?
- What type of event was it?
- Which Stripe object was inside the event?
- Was it processed successfully?
- Did it fail?
- Has this event already been processed?

## Code pattern

```python
save_event(stripe_event_id, event_type, object_id)
```

Then after business logic succeeds:

```python
mark_event_processed(stripe_event_id)
```

If something fails:

```python
mark_event_failed(stripe_event_id, str(e))
```

---

# 6. Duplicate Webhook Protection

## Problem

Webhook events can be delivered more than once.

If the app processes the same event repeatedly, it may cause duplicate side effects.

Examples:

- duplicate emails
- duplicate access grants
- duplicate shipping
- duplicate downstream workflows

## Project solution

The app stores each Stripe event ID and checks whether it was already processed.

## Code pattern

```python
if event_already_processed(stripe_event_id):
    return "Already processed", 200
```

## Important distinction

An event existing in the database is not the same as an event being processed.

Correct logic:

```sql
WHERE stripe_event_id = ? AND processed = 1
```

## Why return 200 for duplicates?

If an event was already processed, the app can safely tell Stripe:

```text
I received this event and no further action is needed.
```

So returning `200` is appropriate.

---

# 7. Metadata and Reconciliation

## Business goal

Trace local orders to Stripe objects and Stripe objects back to local orders.

## Local object

```text
orders.id
```

## Stripe objects

```text
Checkout Session
PaymentIntent
```

## Metadata used

Checkout Session metadata:

```text
order_id
integration_source
```

PaymentIntent metadata:

```text
order_id
product_name
integration_source
```

## Why metadata matters

Metadata creates a reconciliation trail.

It helps answer:

- Which local order belongs to this Checkout Session?
- Which local order belongs to this PaymentIntent?
- Which Stripe payment belongs to this local order?
- How do I debug a mismatch?

## Important lesson

Metadata does not automatically appear everywhere.

If I need metadata on the PaymentIntent, I should explicitly add it through:

```python
payment_intent_data={
    "metadata": {
        "order_id": str(order_id)
    }
}
```

---

# 8. Checkout Session Retrieval with Expanded PaymentIntent

## Business goal

Debug a Checkout Session and inspect the related PaymentIntent.

## Route

```text
/debug/session/<stripe_session_id>
```

## Direction of request

```text
My Flask app → Stripe API
```

## Code pattern

```python
session = stripe.checkout.Session.retrieve(
    stripe_session_id,
    expand=["payment_intent"]
)
```

## What `expand` does

Some Stripe API responses include related object IDs.

For example:

```text
payment_intent = pi_...
```

Using `expand` asks Stripe to return the full related object instead of only the ID.

## Why this matters

With the expanded PaymentIntent, the app can display:

- PaymentIntent ID
- PaymentIntent status
- amount
- currency
- metadata

## Interview answer

If an API response only includes a related object ID, I can retrieve that object separately or use `expand[]` where supported to include the full object in the response.

---

# 9. PaymentIntent Listing and Cursor Pagination

## Business goal

Practice listing Stripe API objects and handling pagination.

## Route

```text
/debug/payment-intents
```

## Direction of request

```text
My Flask app → Stripe API
```

## Code pattern

First page:

```python
stripe.PaymentIntent.list(limit=10)
```

Next page:

```python
stripe.PaymentIntent.list(
    limit=10,
    starting_after="pi_..."
)
```

## Response fields

### `data`

The list of PaymentIntent objects.

### `has_more`

Whether another page exists.

## Pagination model

Stripe uses cursor-based pagination.

It does not use:

```text
page=2
```

Instead, it uses object IDs as cursors.

## How next page works

1. Request a limited number of objects.
2. Check `has_more`.
3. Take the ID of the last object from the current page.
4. Pass that ID as `starting_after`.
5. Retrieve the next page.

## Interview answer

Stripe list APIs use cursor-based pagination. I would request a limited number of objects, check `has_more`, and use the last object ID as `starting_after` to retrieve the next page.

---

# 10. Environment Variables

## Variables used

```bash
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

## `STRIPE_SECRET_KEY`

Used by the backend to call Stripe APIs.

Examples:

- create Checkout Session
- retrieve Checkout Session
- list PaymentIntents

## `STRIPE_PRICE_ID`

Identifies the Stripe Price used in Checkout.

## `STRIPE_WEBHOOK_SECRET`

Used to verify incoming webhook signatures.

## Important distinction

```text
STRIPE_SECRET_KEY = outbound API authentication
STRIPE_WEBHOOK_SECRET = inbound webhook verification
```

## Important local development lesson

After changing `.env`, restart Flask.

---

# 11. Local Debugging Lessons

## `localhost` vs `127.0.0.1`

During webhook testing, `localhost` did not reach Flask correctly.

Using this fixed it:

```bash
./stripe listen --forward-to 127.0.0.1:5000/webhook
```

## Browser issue

At one point, the browser showed a 403 error, but:

```bash
curl -i http://127.0.0.1:5000/events
```

returned:

```text
HTTP/1.1 200 OK
```

This showed the app was working and the issue was browser-specific.

## Stripe object access

This failed:

```python
session.get("payment_intent")
```

This worked:

```python
session.payment_intent
```

Lesson:

Stripe SDK objects are not always normal Python dictionaries.

---

# 12. Strong Project Summary

This project implements a Stripe Checkout flow with local order tracking, webhook-based fulfillment, event logging, duplicate webhook protection, metadata reconciliation, object retrieval with expansion, and PaymentIntent pagination.

The key architecture is:

```text
User clicks Buy
→ Flask creates local pending order
→ Flask creates Stripe Checkout Session
→ Flask stores Stripe Session ID
→ User pays on Stripe Checkout
→ Stripe sends checkout.session.completed webhook
→ Flask verifies webhook signature
→ Flask logs event
→ Flask marks order paid
→ Flask stores PaymentIntent ID
→ Flask marks event processed
```

The project demonstrates:

- API request formation
- webhook handling
- secure signature verification
- local state management
- duplicate event protection
- metadata reconciliation
- object relationships
- cursor pagination
- troubleshooting workflows