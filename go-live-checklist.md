# Stripe Go-Live Checklist

This checklist describes what should be reviewed before moving a Stripe integration from test mode to production.

This project is a learning project, but the checklist reflects real implementation concerns.

---

# 1. Stripe Account Readiness

- [ ] Stripe account is fully activated.
- [ ] Business details are complete.
- [ ] Bank account or payout details are configured.
- [ ] Required verification/KYC information is submitted.
- [ ] Account is not restricted.
- [ ] Team members have appropriate Dashboard access.
- [ ] Test mode and live mode are clearly understood.

---

# 2. API Keys

## Test mode

- [ ] Test secret key was used during development:

```text
sk_test_...
```

- [ ] Test resources were used during development:
  - test Price ID
  - test Checkout Sessions
  - test PaymentIntents
  - test webhooks

## Live mode

- [ ] Live secret key is available:

```text
sk_live_...
```

- [ ] Live publishable key is available if frontend code needs it:

```text
pk_live_...
```

- [ ] Live keys are stored securely.
- [ ] Live keys are not committed to GitHub.
- [ ] `.env` is ignored by Git.
- [ ] Live keys are not printed in logs.
- [ ] Live keys are not exposed in browser/client-side code.

## Environment variables

Production environment should define:

```bash
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

- [ ] Environment variables are configured in the production hosting platform.
- [ ] App is restarted/redeployed after environment changes.

---

# 3. Products and Prices

- [ ] Live Product exists in Stripe Dashboard.
- [ ] Live Price exists in Stripe Dashboard.
- [ ] App uses the live `STRIPE_PRICE_ID`.
- [ ] Currency is correct.
- [ ] Amount is correct.
- [ ] Amount format uses the correct smallest currency unit where applicable.
- [ ] Product name shown to the customer is correct.
- [ ] Tax behavior has been reviewed if relevant.
- [ ] Pricing has been approved by the business.

---

# 4. Checkout Session

- [ ] Checkout Session is created server-side.
- [ ] App uses:

```python
mode="payment"
```

for one-time payments.

- [ ] `success_url` points to the production domain.
- [ ] `cancel_url` points to the production domain.
- [ ] Local order is created before Checkout Session.
- [ ] Local order starts as:

```text
pending
```

- [ ] `stripe_session_id` is saved locally.
- [ ] Checkout Session metadata includes local `order_id`.
- [ ] PaymentIntent metadata includes local `order_id`.

---

# 5. Webhooks

## Endpoint

- [ ] Production webhook endpoint is configured in Stripe Dashboard.
- [ ] Endpoint URL uses HTTPS.
- [ ] Endpoint URL points to:

```text
/webhook
```

- [ ] Production webhook signing secret is copied to production environment.
- [ ] `STRIPE_WEBHOOK_SECRET` starts with:

```text
whsec_...
```

- [ ] App was restarted/redeployed after adding webhook secret.

## Events

Webhook endpoint should listen for required events.

For this project:

- [ ] `checkout.session.completed`

Optional future events:

- [ ] `payment_intent.succeeded`
- [ ] `payment_intent.payment_failed`
- [ ] `charge.refunded`
- [ ] `charge.dispute.created`

## Verification

- [ ] Webhook route uses raw request body.
- [ ] Webhook route verifies `Stripe-Signature`.
- [ ] Invalid signatures return non-2xx.
- [ ] Valid events return 2xx after safe processing.
- [ ] Webhook handler does not rely on the success page.

---

# 6. Fulfillment Logic

- [ ] Success page does not mark order as paid by itself.
- [ ] Order is marked paid only after verified webhook event.
- [ ] `checkout.session.completed` updates local order from:

```text
pending → paid
```

- [ ] PaymentIntent ID is saved locally.
- [ ] Fulfillment action is clearly defined.

Examples of fulfillment actions:

- granting course access
- sending confirmation email
- creating downloadable access
- notifying operations team
- shipping product

- [ ] Fulfillment is safe to retry.
- [ ] Duplicate fulfillment is prevented.

---

# 7. Duplicate Event Protection

- [ ] Stripe event IDs are stored.
- [ ] `stripe_event_id` is unique.
- [ ] New events are stored with:

```text
processed = 0
```

- [ ] Events are marked:

```text
processed = 1
```

only after business logic succeeds.

- [ ] Already processed events are skipped safely.
- [ ] Duplicate events return 2xx.
- [ ] Failed events store error messages.
- [ ] Failed events are not marked as processed.

---

# 8. Logging and Monitoring

- [ ] App logs webhook receipt.
- [ ] App logs webhook failures.
- [ ] App logs order status updates.
- [ ] App logs enough IDs for troubleshooting:
  - local order ID
  - Stripe event ID
  - Checkout Session ID
  - PaymentIntent ID
- [ ] Logs do not include secret keys.
- [ ] Stripe Dashboard webhook logs are monitored.
- [ ] Failed webhook deliveries are reviewed.
- [ ] Alerting exists for repeated webhook failures in production.

---

# 9. Database and Data Integrity

- [ ] Orders table exists in production database.
- [ ] Stripe events table exists in production database.
- [ ] Database migrations/setup are repeatable.
- [ ] Local order statuses are clearly defined.
- [ ] Required fields are not nullable unless intentionally optional.
- [ ] Local order can be matched by `stripe_session_id`.
- [ ] Local order can store `stripe_payment_intent_id`.
- [ ] Metadata `order_id` matches local order ID.
- [ ] Database backups are configured if production data matters.

---

# 10. Error Handling

- [ ] Missing `STRIPE_PRICE_ID` returns a clear error.
- [ ] Missing `STRIPE_SECRET_KEY` is detected.
- [ ] Missing `STRIPE_WEBHOOK_SECRET` is detected.
- [ ] Invalid Checkout Session IDs are handled.
- [ ] Stripe API errors are handled gracefully.
- [ ] Webhook processing errors are logged.
- [ ] Customers do not see raw internal tracebacks in production.
- [ ] Flask debug mode is disabled in production.

---

# 11. Security

- [ ] `.env` is not committed to GitHub.
- [ ] `.venv/` is not committed to GitHub.
- [ ] `orders.db` is not committed if it contains local/test data.
- [ ] Secret keys are rotated if accidentally exposed.
- [ ] Webhook signatures are verified.
- [ ] HTTPS is used in production.
- [ ] Admin/debug routes are not publicly exposed in production.
- [ ] Debug pages are protected or removed before production.
- [ ] Stripe Dashboard access is limited to appropriate users.
- [ ] Principle of least privilege is followed.

---

# 12. Testing Before Launch

## Test successful payment

- [ ] Customer can open Checkout.
- [ ] Customer can complete payment.
- [ ] Order is created as pending.
- [ ] Webhook marks order as paid.
- [ ] PaymentIntent ID is saved.
- [ ] Metadata appears in Stripe Dashboard.

## Test cancel flow

- [ ] Customer can cancel Checkout.
- [ ] Customer returns to cancel page.
- [ ] Order does not become paid.

## Test webhook failure

- [ ] Wrong webhook secret causes signature failure.
- [ ] App returns non-2xx for invalid signature.
- [ ] Error is visible in logs.

## Test duplicate event

- [ ] Resend event with:

```bash
stripe events resend evt_...
```

- [ ] App skips already processed event.
- [ ] Duplicate event returns 2xx.
- [ ] No duplicate fulfillment occurs.

## Test pagination/debugging

- [ ] PaymentIntent listing works.
- [ ] Checkout Session debug page works.
- [ ] Metadata can be verified.

---

# 13. Deployment Readiness

- [ ] App is deployed to production hosting.
- [ ] Production domain is configured.
- [ ] HTTPS certificate is active.
- [ ] Production environment variables are configured.
- [ ] Production database is configured.
- [ ] Debug mode is off.
- [ ] Logs are accessible.
- [ ] Stripe live webhook endpoint is configured.
- [ ] Test mode resources are not used in live environment.
- [ ] Live test transaction plan is approved.

---

# 14. Operational Runbook

- [ ] Troubleshooting runbook exists.
- [ ] Support team knows where to find:
  - local order ID
  - Stripe Checkout Session ID
  - PaymentIntent ID
  - Stripe event ID
- [ ] Refund process is documented.
- [ ] Failed payment process is documented.
- [ ] Customer communication process is documented.
- [ ] Escalation path is documented.

---

# 15. Known Limitations of This Learning Project

This project currently does not include:

- [ ] User authentication
- [ ] Production deployment
- [ ] Email confirmation
- [ ] Refund handling
- [ ] Dispute handling
- [ ] Subscription billing
- [ ] Customer Portal
- [ ] Multiple products
- [ ] Tax calculation
- [ ] Admin authentication
- [ ] Background job queue
- [ ] Production database migrations

These would need to be addressed before a real production launch.

---

# Strong Implementation Consultant Summary

Before going live, I would verify that live API keys, live Price IDs, production webhook endpoints, webhook signature verification, local order persistence, duplicate event protection, metadata reconciliation, logging, monitoring, and error handling are all correctly configured.

I would also confirm that fulfillment is triggered by verified webhooks, not by browser redirects, and that the team has a troubleshooting runbook for failed payments, webhook failures, duplicate events, and reconciliation issues.