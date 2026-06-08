# Broken API Request Lab

This file is for practicing Stripe API troubleshooting.

For each case, I should be able to explain:

- What is broken?
- Why is it broken?
- How would I investigate?
- How would I fix it?
- How would I prevent it in a real implementation?

---

# Case 1 — Wrong API key type

## Scenario

A developer tries to create a Checkout Session from the backend, but the request fails.

They are using this key:

```text
pk_test_...
```

## What is broken?

The developer is using a publishable key for a server-side Stripe API request.

## Why it is broken

A publishable key is intended for client-side or browser use.

Creating a Checkout Session is a backend operation and requires the secret key:

```text
sk_test_...
```

## How I would investigate

- Check the error message returned by Stripe.
- Check whether the key starts with `pk_test_` or `sk_test_`.
- Check whether the request is being made from the frontend or backend.
- Check environment variables in `.env`.
- Check that the backend is loading the correct environment variable.

## Fix

Use the secret key on the backend:

```python
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
```

Make sure `.env` contains:

```bash
STRIPE_SECRET_KEY=sk_test_...
```

## Prevention

- Never hardcode Stripe keys.
- Keep secret keys only on the backend.
- Add `.env` to `.gitignore`.
- Use clear variable names like `STRIPE_SECRET_KEY`.
- Do not expose `sk_test_...` or `sk_live_...` in frontend code.

## Interview answer

A publishable key can identify the account from the browser, but it cannot perform privileged backend operations. Creating a Checkout Session should happen server-side using the secret key. I would check the key prefix, confirm the environment variable, and make sure the secret key is never exposed to the client.

---

# Case 2 — Webhook signature verification fails

## Scenario

Stripe sends webhook events, but the Flask app returns:

```text
400 Invalid signature
```

## What is broken?

The app cannot verify that the webhook request genuinely came from Stripe.

## Likely causes

- The app is using the wrong `whsec_...` webhook secret.
- The Stripe CLI was restarted and printed a new webhook secret.
- `.env` was updated but Flask was not restarted.
- The code is not using the raw request body.
- The JSON payload was parsed or modified before verification.
- The request is being sent to the wrong endpoint or environment.

## How I would investigate

- Check the Stripe CLI terminal for the current `whsec_...`.
- Check `.env` contains the same webhook secret.
- Restart Flask after changing `.env`.
- Confirm the webhook route uses the raw body:

```python
payload = request.data
```

- Confirm verification uses:

```python
stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
```

- Check the Flask terminal for `400 Invalid signature`.
- Check whether the request is being forwarded to the correct route:

```text
/webhook
```

## Fix

Update `.env`:

```bash
STRIPE_WEBHOOK_SECRET=whsec_current_value
```

Then restart Flask:

```bash
CTRL + C
python app.py
```

## Prevention

- Remember that local Stripe CLI webhook secrets can change.
- Restart Flask after `.env` changes.
- Always verify webhook signatures using the raw request body.
- Do not parse or modify JSON before verification.

## Interview answer

Signature verification fails when the app cannot prove that the event came from Stripe. I would first check that the webhook secret matches the current endpoint or CLI listener, then confirm the app uses the raw request body. Parsed or modified JSON can break verification because Stripe signs the exact raw payload.

---

# Case 3 — Payment succeeds but local order remains pending

## Scenario

The customer pays successfully in Stripe, but the app still shows:

```text
status = pending
```

## What is broken?

The app did not successfully process the webhook that should mark the order as paid.

## Possible causes

- Stripe CLI listener is not running.
- Listener is forwarding to the wrong URL.
- `localhost` is not reaching Flask correctly.
- Webhook secret is outdated.
- Signature verification fails.
- The webhook route crashes with a `500`.
- The app cannot find the local order by `stripe_session_id`.
- The database update did not commit.
- The app skipped the event incorrectly due to duplicate-processing logic.

## How I would investigate

1. Confirm payment succeeded in Stripe.
2. Check Stripe CLI output for:

```text
checkout.session.completed
```

3. Check whether Stripe CLI shows:

```text
[200]
[400]
[403]
[500]
```

4. Check Flask terminal for:

```text
POST /webhook
```

5. Confirm listener uses:

```bash
./stripe listen --forward-to 127.0.0.1:5000/webhook
```

6. Confirm `.env` has the current:

```bash
STRIPE_WEBHOOK_SECRET=whsec_...
```

7. Restart Flask after changing `.env`.

8. Check app logs for exceptions.

9. Check `/events` for the event and error.

10. Check `/orders` for matching:

```text
stripe_session_id
```

## Fix

Fix depends on the failure:

- No Flask `POST /webhook` log: fix forwarding URL.
- `400 Invalid signature`: update webhook secret and restart Flask.
- `403`: check whether the request is reaching Flask or being blocked elsewhere.
- `500`: fix the app exception.
- Event received but skipped incorrectly: fix duplicate event logic.
- Order not found: check `stripe_session_id` was saved correctly.
- Database not updated: check SQL update and `conn.commit()`.

## Prevention

- Log webhook events.
- Store event IDs.
- Store `stripe_session_id` on local orders.
- Add troubleshooting visibility through `/orders` and `/events`.
- Add clear app logging for webhook processing.
- Mark events as processed only after business logic succeeds.

## Interview answer

If Stripe shows a successful payment but the local app remains pending, I would debug the webhook path first. I would check whether `checkout.session.completed` was sent, whether my endpoint received it, what status code was returned, whether signature verification passed, and whether the local `stripe_session_id` matched an order. The success page is not the reliable fulfillment trigger; the webhook is.

---

# Case 4 — Duplicate webhook processing

## Scenario

Stripe sends the same `checkout.session.completed` event more than once.

## What is broken?

The app may process the same event multiple times if it does not track processed event IDs.

## Why it matters

Duplicate processing can cause repeated side effects such as:

- sending duplicate emails
- granting access twice
- shipping twice
- triggering duplicate workflows
- writing duplicate fulfillment records

## How I would investigate

- Check whether the same `stripe_event_id` appears more than once.
- Check `/events`.
- Check whether `processed = 1`.
- Check whether the app skips already processed events.
- Resend an event using:

```bash
./stripe events resend evt_...
```

- Watch Flask logs for:

```text
Skipping already processed event
```

## Fix

Store Stripe event IDs and check whether an event was already processed:

```python
if event_already_processed(stripe_event_id):
    return "Already processed", 200
```

Only process events that have not been processed successfully.

## Prevention

- Store `stripe_event_id`.
- Make `stripe_event_id` unique in the database.
- Mark events as processed only after business logic succeeds.
- Make webhook handlers idempotent.
- Return `200` when safely skipping an already processed event.

## Interview answer

Webhook delivery is not guaranteed to be exactly once. Stripe may retry an event if it does not receive a successful response. I would store the Stripe event ID and mark it as processed only after the business logic succeeds. If the same event arrives again, the app should return `200` but skip duplicate processing.

---

# Case 5 — Metadata missing from PaymentIntent

## Scenario

The Checkout Session has local `order_id` metadata, but the PaymentIntent does not.

## What is broken?

Metadata was added only to the Checkout Session, not to the underlying PaymentIntent.

## Why it matters

If I later inspect a PaymentIntent or handle a PaymentIntent event, I may not be able to trace it back to my local order.

For example:

```text
payment_intent.succeeded
payment_intent.payment_failed
```

are PaymentIntent events, not Checkout Session events.

## How I would investigate

- Open the Checkout Session in Stripe Dashboard.
- Open the related PaymentIntent.
- Compare metadata on both objects.
- Use the local debug route:

```text
/debug/session/cs_test_...
```

- Confirm local `/orders` has:
  - local order ID
  - `stripe_session_id`
  - `stripe_payment_intent_id`

## Fix

Add metadata to `payment_intent_data` when creating the Checkout Session:

```python
payment_intent_data={
    "metadata": {
        "order_id": str(order_id),
        "product_name": "Baby Cardigan",
        "integration_source": "stripe_ic_lab"
    }
}
```

## Prevention

Decide where metadata belongs based on which Stripe objects and events I will use later.

For this project:

- Checkout Session metadata helps with Checkout events.
- PaymentIntent metadata helps with payment lifecycle events.

## Interview answer

I would not assume metadata automatically appears on every related Stripe object. If I need to reconcile PaymentIntent events back to my internal order, I should explicitly add the local order ID to `payment_intent_data.metadata` when creating the Checkout Session.

---

# Case 6 — Wrong amount format

## Scenario

A developer creates a price or payment request using:

```text
19.99
```

but Stripe expects:

```text
1999
```

## What is broken?

The amount is being passed in the wrong format.

## Why it is broken

Stripe amount fields often expect the smallest currency unit.

For EUR:

```text
€19.99 = 1999 cents
```

For EUR 50.00:

```text
€50.00 = 5000 cents
```

## How I would investigate

- Check the Stripe API docs for the specific amount field.
- Check whether the field expects an integer.
- Check whether the currency uses minor units.
- Check local database field names.
- Check if the app stores euros or cents.

## Fix

Use integer minor units:

```text
1999
```

not:

```text
19.99
```

## Prevention

- Store amounts consistently.
- Name fields clearly, for example:
  - `amount_cents`
  - `amount_minor_units`
- Validate amount format before sending API requests.
- Avoid mixing display amounts and API amounts.

## Interview answer

I would check whether the Stripe field expects an integer in the smallest currency unit. Many Stripe amount fields expect cents for EUR and USD, so `19.99` should usually be sent as `1999`. I would also name local database fields clearly to avoid mixing display values with API values.

---

# Case 7 — Wrong local webhook forwarding address

## Scenario

Stripe CLI shows webhook events being forwarded, but Flask does not show any:

```text
POST /webhook
```

logs.

Stripe CLI may show something like:

```text
[403] POST http://localhost:5000/webhook
```

but Flask shows nothing.

## What is broken?

The webhook request is not actually reaching the Flask app.

## Possible causes

- The CLI is forwarding to the wrong address.
- `localhost` resolves differently than expected.
- Flask is listening on `127.0.0.1`.
- The wrong port is being used.
- Flask is not running.
- Another service is using the port.

## How I would investigate

- Check Flask terminal for:

```text
Running on http://127.0.0.1:5000
```

- Check whether Flask logs:

```text
POST /webhook
```

- Test the app with:

```bash
curl -i http://127.0.0.1:5000/events
```

- Confirm Stripe CLI forwarding target.

## Fix

Use an explicit forwarding address:

```bash
./stripe listen --forward-to 127.0.0.1:5000/webhook
```

instead of:

```bash
./stripe listen --forward-to localhost:5000/webhook
```

## Prevention

- Use `127.0.0.1` explicitly during local webhook testing.
- Confirm Flask and Stripe CLI use the same port.
- Watch both terminals during tests.
- Use `curl` to confirm Flask is reachable.

## Interview answer

If Stripe CLI shows forwarding but Flask does not log the webhook request, I would suspect the request is not reaching my Flask server. I would verify the forwarding URL, port, and local address. In local testing, using `127.0.0.1` instead of `localhost` can remove ambiguity.

---

# Case 8 — Stripe object access error

## Scenario

The webhook route crashes with:

```text
AttributeError: get
```

from code like:

```python
stripe_payment_intent_id = session.get("payment_intent")
```

## What is broken?

The code treats a Stripe object like a normal Python dictionary.

## Why it is broken

The Stripe Python library returns Stripe objects that often use attribute access.

So this may fail:

```python
session.get("payment_intent")
```

while this works:

```python
session.payment_intent
```

## How I would investigate

- Read the Flask traceback.
- Identify the exact failing line.
- Print or inspect the object type.
- Compare how other code accesses Stripe object fields.
- Check whether the object supports dictionary-style access, attribute access, or both.

## Fix

Use attribute access:

```python
stripe_session_id = session.id
stripe_payment_intent_id = session.payment_intent
```

## Prevention

- Be consistent with Stripe object access.
- Use attribute access for Stripe SDK objects in this project.
- Read tracebacks carefully.
- Add small debug prints when unsure.

## Interview answer

The error came from treating the Stripe SDK object like a plain dictionary. I would inspect the traceback, identify the field access that failed, and use the correct access pattern for the SDK object, such as `session.payment_intent`.

---

# Case 9 — Event saved but not processed

## Scenario

The `/events` page shows:

```text
checkout.session.completed
processed = No
error = None
```

The `/orders` page still shows:

```text
status = pending
```

## What is broken?

The event was saved to the database, but the business logic was skipped.

## Root cause example

The app saves the event first:

```python
save_event(stripe_event_id, event_type, object_id)
```

Then checks:

```python
if event_already_processed(stripe_event_id):
    return "Already processed", 200
```

If `event_already_processed()` checks only whether the event exists, it will return `True` immediately after saving.

That causes the app to skip processing a new event.

## How I would investigate

- Check `/events` for:
  - event type
  - processed value
  - error value
- Check `/orders` for:
  - status
  - PaymentIntent ID
- Read the webhook route order of operations.
- Inspect `event_already_processed()`.
- Confirm it checks:

```sql
processed = 1
```

not just event existence.

## Fix

Make `event_already_processed()` check only successfully processed events:

```python
def event_already_processed(stripe_event_id):
    conn = get_db_connection()

    event = conn.execute(
        """
        SELECT id FROM stripe_events
        WHERE stripe_event_id = ? AND processed = 1
        """,
        (stripe_event_id,)
    ).fetchone()

    conn.close()

    return event is not None
```

Also make `save_event()` safe for duplicates:

```python
def save_event(stripe_event_id, event_type, object_id):
    conn = get_db_connection()

    conn.execute(
        """
        INSERT OR IGNORE INTO stripe_events (
            stripe_event_id,
            event_type,
            object_id,
            processed
        )
        VALUES (?, ?, ?, ?)
        """,
        (stripe_event_id, event_type, object_id, 0)
    )

    conn.commit()
    conn.close()
```

## Prevention

- Define clearly what “already processed” means.
- Do not confuse “event exists” with “event was processed successfully.”
- Store `processed = 0` for new events.
- Store `processed = 1` only after business logic succeeds.
- Add tests for resending events.

## Interview answer

An event existing in the database does not necessarily mean it was processed. I would check the `processed` flag, not just the event ID. New events should be inserted with `processed = 0`, processed only once, then updated to `processed = 1` after the business logic succeeds.

---

# Case 10 — Browser shows 403 but Flask works with curl

## Scenario

The browser shows:

```text
HTTP ERROR 403
Access to 127.0.0.1 was denied
```

but running:

```bash
curl -i http://127.0.0.1:5000/events
```

returns:

```text
HTTP/1.1 200 OK
```

## What is broken?

The Flask app is working. The issue is browser-specific.

## Possible causes

- Browser cached a bad redirect.
- Browser cached an HTTPS version.
- Browser stored site/security state for `127.0.0.1`.
- Wrong URL was typed or autocompleted.
- The browser is using `https://` instead of `http://`.

## How I would investigate

- Confirm Flask terminal shows:

```text
Running on http://127.0.0.1:5000
```

- Use curl:

```bash
curl -i http://127.0.0.1:5000/events
```

- Check whether Flask logs a browser request.
- Try an incognito/private window.
- Try:

```text
http://localhost:5000/events
```

## Fix

Use the exact URL:

```text
http://127.0.0.1:5000/events
```

or open in an incognito/private window.

If needed, clear browser site data for:

```text
127.0.0.1
localhost
```

## Prevention

- Use exact local URLs.
- Avoid browser autocomplete when switching between ports or protocols.
- Use curl to distinguish browser issues from app issues.

## Interview answer

If curl returns `200 OK` but the browser shows `403`, the Flask app is likely working and the problem is browser-specific. I would confirm whether the request reaches Flask, test with curl, and try a clean browser session or incognito window.

---

# Case 11 — New webhook secret after restarting Stripe CLI

## Scenario

Webhooks stop working after restarting:

```bash
./stripe listen --forward-to 127.0.0.1:5000/webhook
```

## What is broken?

The app may still be using an old webhook signing secret.

## Why it happens

When using Stripe CLI locally, the listener prints a `whsec_...` value.

If the listener session changes and the CLI gives a new `whsec_...`, the Flask app must use that current value.

## How I would investigate

- Look at the current Stripe CLI terminal.
- Copy the current `whsec_...`.
- Compare it to:

```bash
STRIPE_WEBHOOK_SECRET=...
```

in `.env`.

- Check whether Flask was restarted after changing `.env`.

## Fix

Update `.env`:

```bash
STRIPE_WEBHOOK_SECRET=whsec_current_value
```

Then restart Flask:

```bash
CTRL + C
python app.py
```

## Prevention

- Treat the local CLI webhook secret as session-specific.
- Update `.env` when the CLI gives a new secret.
- Restart Flask after `.env` changes.
- Do not confuse `STRIPE_SECRET_KEY` with `STRIPE_WEBHOOK_SECRET`.

## Interview answer

The Stripe secret key and webhook secret have different jobs. The secret key lets my app call Stripe APIs. The webhook secret verifies inbound webhook signatures. If the local CLI webhook secret changes and Flask still uses the old value, signature verification can fail.

---

# Case 12 — Missing or wrong Price ID

## Scenario

The app fails when creating Checkout and returns an error related to the price.

The `.env` value is missing or wrong:

```bash
STRIPE_PRICE_ID=
```

or:

```bash
STRIPE_PRICE_ID=price_wrong...
```

## What is broken?

The app is trying to create a Checkout Session with a missing or invalid Stripe Price ID.

## Why it matters

When using:

```python
"price": price_id
```

Stripe expects a real Price ID from the correct Stripe account and mode.

For test mode, the Price ID should usually start with:

```text
price_...
```

and belong to the same account/environment as the secret key.

## How I would investigate

- Check `.env` has:

```bash
STRIPE_PRICE_ID=price_...
```

- Confirm Flask loads it:

```python
price_id = os.getenv("STRIPE_PRICE_ID")
```

- Check for the safety guard:

```python
if not price_id:
    return "Price ID not set in environment variables", 500
```

- Confirm the Price exists in Stripe Dashboard.
- Confirm it belongs to test mode if using `sk_test_...`.
- Confirm the Price belongs to the same Stripe account.

## Fix

Set the correct Price ID in `.env`:

```bash
STRIPE_PRICE_ID=price_...
```

Then restart Flask:

```bash
CTRL + C
python app.py
```

## Prevention

- Store Price IDs in `.env`.
- Avoid hardcoding Price IDs.
- Keep test keys and test Price IDs together.
- Add startup or route checks for missing environment variables.

## Interview answer

If Checkout creation fails around the price, I would verify that the Price ID exists, belongs to the same account and environment as the secret key, and is loaded correctly from `.env`. A test secret key should be used with test-mode resources.

---

# Case 13 — Environment variable changed but app still uses old value

## Scenario

A developer updates `.env`, but the app behavior does not change.

Example:

```bash
STRIPE_WEBHOOK_SECRET=whsec_new_value
```

but the app still fails signature verification.

## What is broken?

Flask was not restarted after changing `.env`.

## Why it happens

The app loads `.env` when it starts:

```python
load_dotenv()
```

If `.env` changes while Flask is already running, the app may still be using the old value.

## How I would investigate

- Check the `.env` file.
- Restart Flask.
- Add temporary debug logging for whether a value exists, without printing secrets.
- Confirm the app uses:

```python
os.getenv("STRIPE_WEBHOOK_SECRET")
```

## Fix

Restart Flask:

```bash
CTRL + C
python app.py
```

## Prevention

- Restart the app after changing `.env`.
- Avoid changing secrets while assuming the running process has reloaded them.
- Use clear setup notes in README.

## Interview answer

Environment variables are usually read when the app process starts. If I change `.env`, I need to restart the Flask app so it loads the new values. Otherwise, it may keep using an old webhook secret or Price ID.

---

# Case 14 — Success page used as fulfillment source

## Scenario

The app marks orders as paid from the success page instead of the webhook.

## What is broken?

The app is relying on the browser redirect as the source of truth for fulfillment.

## Why it is broken

A customer may pay successfully but never reach the success page.

Reasons include:

- browser closes
- network drops
- redirect fails
- user navigates away
- page load blocked

## How I would investigate

- Check whether order status changes inside the `/success` route.
- Check whether webhook events are being used.
- Check whether `checkout.session.completed` marks the order paid.
- Test payment with webhook listener stopped.

## Fix

Use the success page for user experience only.

Use the webhook to update order status:

```python
if event_type == "checkout.session.completed":
    mark_order_paid_by_session(stripe_session_id)
```

## Prevention

- Treat webhooks as the fulfillment source.
- Treat redirects as user experience.
- Document the order lifecycle:
  - pending before payment
  - paid after verified webhook

## Interview answer

The success page is not a reliable fulfillment trigger because it depends on the customer’s browser returning to the app. A server-to-server webhook is more reliable. I would mark the order as paid only after receiving and verifying the relevant Stripe webhook event.

---

# Case 15 — Wrong event chosen for fulfillment

## Scenario

The app listens to many Stripe events but does not clearly decide which event should update the order.

## What is broken?

The app may update local state from the wrong event or from multiple events inconsistently.

## Why it matters

Stripe sends several events during a successful payment, for example:

```text
payment_intent.created
charge.succeeded
payment_intent.succeeded
checkout.session.completed
charge.updated
```

If the app processes several of them for the same business action, duplicate or inconsistent state changes can happen.

## How I would investigate

- Check `/events` to see which events arrived.
- Check webhook route logic.
- Identify which event changes order status.
- Confirm only one event is responsible for fulfillment.

## Fix

For this Checkout project, use:

```text
checkout.session.completed
```

as the event that marks the local order as paid.

Log other events, but do not use them for the same fulfillment action.

## Prevention

- Define a clear event-to-business-action mapping.
- Document which event updates which local state.
- Avoid processing multiple events for the same side effect.
- Make handlers idempotent.

## Interview answer

Stripe may send multiple events for one payment. I would define one clear fulfillment event to update my local order state. In this Checkout integration, I use `checkout.session.completed` to mark the order paid and log other events for visibility.

---

# Personal project bugs I encountered

## Bug 1 — `localhost` forwarding did not reach Flask

### Symptom

Stripe CLI showed webhook forwarding, but Flask did not show `POST /webhook`.

### Fix

Changed:

```bash
./stripe listen --forward-to localhost:5000/webhook
```

to:

```bash
./stripe listen --forward-to 127.0.0.1:5000/webhook
```

### Lesson

When debugging local webhooks, verify that the request actually reaches Flask.

---

## Bug 2 — Stripe object `.get()` failed

### Symptom

Flask showed:

```text
AttributeError: get
```

### Fix

Changed:

```python
session.get("payment_intent")
```

to:

```python
session.payment_intent
```

### Lesson

Stripe SDK objects are not always normal Python dictionaries.

---

## Bug 3 — Event saved but skipped before processing

### Symptom

`/events` showed:

```text
checkout.session.completed
processed = No
error = None
```

`/orders` showed:

```text
pending
```

### Fix

Changed `event_already_processed()` so it checks:

```sql
processed = 1
```

not just whether the event exists.

### Lesson

An event existing in the database is not the same as an event being successfully processed.

---

## Bug 4 — Old webhook secret

### Symptom

Webhooks stopped working after restarting Stripe CLI.

### Fix

Copied the current `whsec_...` from Stripe CLI into `.env` and restarted Flask.

### Lesson

Local Stripe CLI webhook secrets can change between listener sessions.
````
