# Stripe Implementation Consultant Talking Points

This file helps me explain the project clearly in an interview.

The goal is to practice explaining both the technical implementation and the business reasoning behind it.

---

# 60-Second Project Summary

I built a Flask-based Stripe Checkout integration for a small product purchase flow.

The app creates a local pending order, creates a Stripe Checkout Session, redirects the customer to Stripe-hosted Checkout, receives a verified webhook after payment, logs the Stripe event, marks the local order as paid, stores the PaymentIntent ID, and displays debugging views for orders, events, Checkout Sessions, and PaymentIntents.

I also added metadata to both the Checkout Session and PaymentIntent so I can reconcile Stripe objects back to my local order records. The project includes duplicate webhook protection, cursor-based pagination, a troubleshooting runbook, a go-live checklist, and a broken API request lab.

---

# 1. Why did I choose Stripe Checkout?

I chose Stripe Checkout because it provides a Stripe-hosted payment page.

This reduces the amount of payment UI and compliance-sensitive card handling that my app needs to build directly.

In this project, my backend creates a Checkout Session and Stripe handles the hosted payment experience.

## Strong answer

Stripe Checkout is a good fit when a business wants to accept payments quickly using a prebuilt hosted payment page. It reduces implementation complexity while still allowing my backend to create orders, attach metadata, receive webhooks, and reconcile payments.

---

# 2. What happens when the user clicks Buy?

The flow is:

```text
User clicks Buy
→ Flask creates a local order with status pending
→ Flask creates a Stripe Checkout Session
→ Flask stores the Stripe Session ID on the local order
→ User is redirected to Stripe Checkout
```

The local order is created first so my app has its own internal record before sending the customer away to Stripe.

## Strong answer

When the customer starts checkout, I create a local pending order first. Then I create the Stripe Checkout Session and store the returned `stripe_session_id` against that order. This gives my app a reliable way to match future Stripe webhook events back to the local order.

---

# 3. Why create a local order before payment is complete?

Because the app needs its own source of truth.

Stripe knows about the payment, but my application needs to track:

- local order ID
- product
- amount
- status
- Stripe Checkout Session ID
- Stripe PaymentIntent ID

The order starts as:

```text
pending
```

and later becomes:

```text
paid
```

after a verified webhook.

## Strong answer

I create a local pending order before redirecting to Stripe so the application can track the purchase attempt independently. After Stripe creates the Checkout Session, I store the Stripe Session ID on the order. This creates a link between my internal order and the Stripe payment flow.

---

# 4. Why is the success page not enough?

The success page depends on the customer’s browser returning to my app.

A customer could pay successfully but never reach the success page because:

- the browser closes
- the redirect fails
- the network drops
- the customer navigates away

Therefore, the success page is useful for user experience, but not reliable for fulfillment.

## Strong answer

I would not fulfill orders from the success redirect alone. The success page is browser-dependent. The reliable confirmation should come from a server-to-server webhook from Stripe, such as `checkout.session.completed`.

---

# 5. What is a webhook?

A webhook is an HTTP endpoint in my app that another service calls automatically when an event happens.

In this project:

```text
Stripe → Flask /webhook
```

Stripe sends webhook events to my app when payment-related events occur.

## Strong answer

A webhook reverses the normal API direction. Instead of my app calling Stripe, Stripe calls my app to notify it that something happened. In this project, Stripe sends `checkout.session.completed` to my `/webhook` route when the customer completes Checkout.

---

# 6. What event marks the order paid?

The app uses:

```text
checkout.session.completed
```

This means the customer completed the Stripe Checkout flow.

When my app receives this verified event, it:

1. Extracts the Checkout Session ID.
2. Extracts the PaymentIntent ID.
3. Finds the local order by `stripe_session_id`.
4. Marks the order as paid.
5. Saves the PaymentIntent ID.
6. Marks the event as processed.

## Strong answer

For this Checkout integration, I use `checkout.session.completed` as the fulfillment event. Once the event is verified, I use the Checkout Session ID to find the matching local order and update it from pending to paid.

---

# 7. What does signature verification protect against?

Webhook endpoints are publicly reachable.

Signature verification protects the app from processing fake, spoofed, or tampered webhook requests.

The app verifies:

- raw request body
- `Stripe-Signature` header
- `STRIPE_WEBHOOK_SECRET`

## Strong answer

I do not trust webhook JSON just because it looks like a Stripe event. I verify the Stripe signature using the raw request body and webhook secret. This confirms the event came from Stripe and was not modified before my app processes it.

---

# 8. Why use the raw request body?

Stripe signs the exact raw request payload.

If the app parses or modifies JSON before verification, the payload bytes can change and signature verification may fail.

That is why the webhook route uses:

```python
payload = request.data
```

## Strong answer

Stripe signature verification depends on the exact raw body. If I parse or mutate the JSON before verification, the signature may no longer match. So I pass `request.data` directly to `stripe.Webhook.construct_event()`.

---

# 9. What is the difference between `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`?

```text
STRIPE_SECRET_KEY
```

lets my backend call Stripe APIs.

Examples:

- create Checkout Session
- retrieve Checkout Session
- list PaymentIntents

```text
STRIPE_WEBHOOK_SECRET
```

lets my backend verify incoming webhook events from Stripe.

## Strong answer

The Stripe secret key is for outbound API authentication from my app to Stripe. The webhook secret is for inbound webhook verification from Stripe to my app. They are different secrets with different purposes.

---

# 10. Why log Stripe event IDs?

Stripe event IDs uniquely identify webhook events.

They look like:

```text
evt_...
```

Logging them helps answer:

- Did my app receive this event?
- Was it processed?
- Did it fail?
- Was it already processed?
- Which Stripe object was inside it?

## Strong answer

I log Stripe event IDs because webhook delivery may be retried. The event ID gives me a stable unique key to detect duplicate deliveries, prevent duplicate processing, and troubleshoot event handling.

---

# 11. What is duplicate webhook protection?

Webhook events can be delivered more than once.

The app stores each event ID and checks whether it was already processed.

If the event was already processed, the app skips it safely and returns `200`.

## Strong answer

Webhook handlers should be idempotent. If Stripe sends the same event twice, my app should not repeat fulfillment. I store event IDs and only process events that have not already been successfully processed.

---

# 12. What is the difference between idempotency keys and webhook duplicate protection?

## Idempotency keys

Direction:

```text
My app → Stripe
```

They protect Stripe-side operations when my app retries outbound API requests.

Example:

```text
My app tries to create a Checkout Session.
Network times out.
My app retries.
Idempotency key prevents duplicate Stripe-side creation.
```

## Webhook duplicate protection

Direction:

```text
Stripe → My app
```

It protects app-side operations when Stripe sends the same event more than once.

Example:

```text
Stripe sends checkout.session.completed twice.
My app should not fulfill twice.
```

## Strong answer

Idempotency keys protect outbound API requests my app sends to Stripe. Webhook duplicate protection protects inbound events Stripe sends to my app. Both reduce duplicate effects, but they apply in opposite directions.

---

# 13. Why use metadata?

Metadata creates a reconciliation path between local records and Stripe objects.

In this project, I store the local `order_id` on:

- Checkout Session metadata
- PaymentIntent metadata

I also store Stripe IDs locally:

- `stripe_session_id`
- `stripe_payment_intent_id`

## Strong answer

I use metadata to connect internal business records to Stripe objects. This lets me trace a local order to a Checkout Session or PaymentIntent, and also trace a Stripe payment back to the local order.

---

# 14. Why put metadata on both Checkout Session and PaymentIntent?

Checkout Session metadata helps with Checkout-related events, such as:

```text
checkout.session.completed
```

PaymentIntent metadata helps with payment lifecycle events, such as:

```text
payment_intent.succeeded
payment_intent.payment_failed
```

## Strong answer

Metadata does not automatically appear everywhere I might need it. If I plan to inspect or handle PaymentIntent events, I should explicitly put the local order ID on the PaymentIntent using `payment_intent_data.metadata`.

---

# 15. What does `expand` do?

Some Stripe API responses include related object IDs instead of full objects.

For example:

```text
payment_intent = pi_...
```

Using `expand` asks Stripe to include the full related object.

In this project:

```python
stripe.checkout.Session.retrieve(
    stripe_session_id,
    expand=["payment_intent"]
)
```

## Strong answer

If a Stripe response only includes a related object ID, I can retrieve that object separately or use `expand[]` where supported to include the full object in the same response. I used this to inspect the PaymentIntent from a Checkout Session.

---

# 16. How does Stripe pagination work?

Stripe list APIs use cursor-based pagination.

The response includes:

- `data`
- `has_more`

The next page uses:

```python
starting_after="pi_..."
```

where the value is the last object ID from the current page.

## Strong answer

Stripe does not use page-number pagination like `page=2`. I request a limited number of objects, check `has_more`, and pass the last object ID as `starting_after` to retrieve the next page.

---

# 17. How would I troubleshoot “payment succeeded but order is pending”?

I would check:

1. Did the payment succeed in Stripe?
2. Did Stripe send `checkout.session.completed`?
3. Did the Stripe CLI or Dashboard show a successful webhook delivery?
4. Did Flask receive `POST /webhook`?
5. Was the response `200`, `400`, `403`, or `500`?
6. Did signature verification pass?
7. Did the event appear in `/events`?
8. Was the event marked processed?
9. Does the event object ID match the local `stripe_session_id`?
10. Did the database update commit?

## Strong answer

I would debug the webhook path first. A successful payment in Stripe does not guarantee the local app processed the event. I would trace from Stripe event delivery to Flask logs, event storage, signature verification, order matching, and database update.

---

# 18. What real bugs did I fix?

## Bug 1 — Local forwarding

Problem:

```text
localhost:5000/webhook
```

did not reach Flask.

Fix:

```bash
./stripe listen --forward-to 127.0.0.1:5000/webhook
```

## Bug 2 — Stripe object access

Problem:

```python
session.get("payment_intent")
```

caused:

```text
AttributeError: get
```

Fix:

```python
session.payment_intent
```

## Bug 3 — Event saved but skipped

Problem:

The app saved an event, then immediately treated it as already processed.

Fix:

Check:

```sql
processed = 1
```

not just event existence.

## Bug 4 — Old webhook secret

Problem:

Stripe CLI printed a new `whsec_...`, but Flask was still using the old one.

Fix:

Update `.env` and restart Flask.

---

# 19. What would need to change before production?

This project is not production-ready yet.

Before production, I would review:

- live API keys
- production webhook endpoint
- HTTPS
- production database
- admin route protection
- debug route removal or authentication
- logging and monitoring
- error handling
- refund process
- dispute process
- email/customer communication
- deployment security
- secret management

## Strong answer

The project demonstrates the integration pattern, but production would require secure deployment, protected admin/debug routes, real database infrastructure, monitoring, error handling, and operational processes for refunds, disputes, and failed payments.

---

# 20. Final interview summary

I built a Stripe Checkout integration that creates local pending orders, redirects users to Stripe-hosted Checkout, verifies webhooks, marks orders paid from `checkout.session.completed`, logs Stripe events, prevents duplicate webhook processing, stores PaymentIntent IDs, uses metadata for reconciliation, retrieves expanded Stripe objects for debugging, and lists PaymentIntents using cursor-based pagination.

This project helped me practice reading API docs, forming API requests, debugging broken requests, handling asynchronous workflows, explaining object relationships, and documenting go-live considerations.