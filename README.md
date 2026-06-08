# Stripe Implementation Consultant API Lab

A Flask-based Stripe Checkout integration project built to practice technical API implementation skills relevant to Stripe Implementation Consultant interviews.

This project demonstrates:

- Stripe Checkout Session creation
- Local order tracking with SQLite
- Webhook-based fulfillment
- Webhook signature verification
- Webhook event logging
- Duplicate webhook protection
- Metadata reconciliation
- Checkout Session retrieval with expanded PaymentIntent
- PaymentIntent listing with cursor-based pagination
- API troubleshooting documentation
- Go-live planning documentation

---

# Business Scenario

A small product business wants to sell a product online using Stripe Checkout.

The business needs to:

1. Create a checkout flow.
2. Track local orders.
3. Confirm payment reliably.
4. Reconcile local orders with Stripe payments.
5. Troubleshoot webhook and API issues.
6. Prepare for production go-live.

The sample product used in this project is:

```text
Baby Cardigan
```

---

# Architecture Overview

```text
User clicks Buy
→ Flask creates local pending order
→ Flask creates Stripe Checkout Session
→ Flask stores Stripe Session ID
→ User pays on Stripe Checkout
→ Stripe sends checkout.session.completed webhook
→ Flask verifies webhook signature
→ Flask logs Stripe event
→ Flask marks local order as paid
→ Flask stores PaymentIntent ID
→ Event is marked as processed
```

---

# Tech Stack

- Python
- Flask
- SQLite
- Stripe Python SDK
- Stripe CLI
- HTML templates
- python-dotenv
- Git/GitHub

---

# Main Features

## 1. Checkout Session Creation

The app creates a Stripe Checkout Session when the user clicks Buy.

The app also creates a local order before redirecting the user to Stripe.

Local order starts as:

```text
pending
```

After Stripe creates the Checkout Session, the app stores:

```text
stripe_session_id
```

---

## 2. Webhook Fulfillment

The app handles:

```text
checkout.session.completed
```

When this event is received and verified, the app updates the local order:

```text
pending → paid
```

The app also stores:

```text
stripe_payment_intent_id
```

---

## 3. Webhook Signature Verification

The webhook route verifies incoming Stripe events using:

- raw request body
- `Stripe-Signature` header
- `STRIPE_WEBHOOK_SECRET`

This protects the app from fake or tampered webhook requests.

---

## 4. Event Logging

Webhook events are stored in a local table:

```text
stripe_events
```

The app records:

- Stripe event ID
- event type
- Stripe object ID
- processed status
- error message
- created timestamp

---

## 5. Duplicate Webhook Protection

The app stores Stripe event IDs and skips events that were already processed.

This prevents duplicate side effects such as:

- duplicate fulfillment
- duplicate emails
- duplicate access grants
- duplicate downstream workflows

---

## 6. Metadata and Reconciliation

The app stores the local order ID in Stripe metadata.

Checkout Session metadata includes:

```text
order_id
integration_source
```

PaymentIntent metadata includes:

```text
order_id
product_name
integration_source
```

This allows local orders and Stripe payments to be traced in both directions.

---

## 7. Debug Routes

The project includes several local debug pages.

```text
/orders
```

Displays local orders.

```text
/events
```

Displays received Stripe webhook events.

```text
/debug/session/<stripe_session_id>
```

Retrieves a Checkout Session from Stripe and expands the related PaymentIntent.

```text
/debug/payment-intents
```

Lists recent PaymentIntents using cursor-based pagination.

---

# Environment Variables

Create a `.env` file in the project root:

```bash
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

Important:

```text
.env should not be committed to GitHub.
```

---

# Local Setup

## 1. Create and activate virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

## 3. Create local database

```bash
python init_db.py
```

## 4. Run Flask

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

---

# Running Webhooks Locally

Start Stripe CLI listener:

```bash
./stripe listen --forward-to 127.0.0.1:5000/webhook
```

The CLI will print a webhook signing secret:

```text
whsec_...
```

Copy that value into `.env`:

```bash
STRIPE_WEBHOOK_SECRET=whsec_...
```

Then restart Flask:

```bash
CTRL + C
python app.py
```

---

# Testing Payments

Use Stripe test card:

```text
4242 4242 4242 4242
```

Use:

```text
Any future expiry
Any CVC
Any valid postal code
```

Expected result:

```text
/orders shows the latest order as paid
/events shows checkout.session.completed as processed
```

---

# Testing Duplicate Webhook Handling

Find a processed event ID from:

```text
/events
```

Then resend it:

```bash
./stripe events resend evt_...
```

Expected result:

```text
The app skips the already processed event and returns 200.
```

---

# API Concepts Practiced

This project practices:

- REST API request formation
- API authentication
- environment variables
- webhook handling
- signature verification
- asynchronous event processing
- idempotent webhook design
- metadata reconciliation
- object expansion
- cursor-based pagination
- debugging API failures
- operational runbook writing

---

# Documentation Files

This repo includes:

```text
api-notes.md
```

Technical notes on the Stripe API concepts used.

```text
broken-api-cases.md
```

Interview-style broken API request cases and answers.

```text
troubleshooting-runbook.md
```

Operational troubleshooting guide.

```text
go-live-checklist.md
```

Production readiness checklist.

```text
talking-points.md
```

Interview explanation and project talking points.

---

# Known Limitations

This is a learning project, not a production-ready app.

It does not currently include:

- user authentication
- protected admin routes
- production deployment
- production database
- email confirmation
- refund handling
- dispute handling
- subscription billing
- Customer Portal
- tax handling
- background job queue
- admin authorization

---

# Interview Summary

I built a Stripe Checkout integration that creates local pending orders, redirects customers to Stripe-hosted Checkout, verifies webhook events, marks orders paid from `checkout.session.completed`, logs Stripe events, prevents duplicate webhook processing, stores PaymentIntent IDs, uses metadata for reconciliation, retrieves expanded Stripe objects for debugging, and lists PaymentIntents using cursor-based pagination.

This project demonstrates practical Stripe API implementation, debugging, documentation, and customer-facing technical explanation skills.