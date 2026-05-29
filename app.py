import os
import sqlite3
import stripe

from flask import Flask, render_template, redirect, request, url_for
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect("orders.db")
    conn.row_factory = sqlite3.Row
    return conn
#Creates a new order record in the database with the initial status "pending" when the user initiates the checkout process, to track the order and link it with the Stripe session for later updates and fulfillment
def create_order():
    conn = get_db_connection()

    cursor = conn.execute(
        """
        INSERT INTO orders (product_name, amount, currency, status)
        VALUES (?, ?, ?, ?)
        """,
        ("Baby Cardigan", 50, "eur", "pending")
    )

    order_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return order_id

#Updates the order record with the Stripe session ID after creating the checkout session, to link the order with the Stripe session for later reference and tracking
def update_order_with_session(order_id, stripe_session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orders
        SET stripe_session_id = ?
        WHERE id = ?
    """, (stripe_session_id, order_id))
    conn.commit()
    conn.close()

#Updates the order record with the Stripe session ID after creating the checkout session, to link the order with the Stripe session for later reference and tracking
def update_order_with_payment_intent(order_id, stripe_payment_intent_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orders
        SET stripe_payment_intent_id = ?
        WHERE id = ?
    """, (stripe_payment_intent_id, order_id))
    conn.commit()
    conn.close()

#Marks the order as paid in the database when the Stripe checkout session is completed, to keep the order status in sync with the payment status and allow for accurate order tracking and fulfillment
def mark_order_paid_by_session(stripe_session_id):
    conn = get_db_connection()

    conn.execute(
        """
        UPDATE orders
        SET status = ?
        WHERE stripe_session_id = ?
        """,
        ("paid", stripe_session_id)
    )

    conn.commit()
    conn.close()

#Records the Stripe payment intent ID in the order record when it becomes available, to allow for easier tracking and troubleshooting of payments in the dashboard and database
def update_payment_intent_by_session(stripe_session_id, stripe_payment_intent_id):
    conn = get_db_connection()

    conn.execute(
        """
        UPDATE orders
        SET stripe_payment_intent_id = ?
        WHERE stripe_session_id = ?
        """,
        (stripe_payment_intent_id, stripe_session_id)
    )

    conn.commit()
    conn.close()

# checks whether we already successfully handled this Stripe event
def event_already_processed(stripe_event_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM stripe_events WHERE stripe_event_id = ? AND processed = 1
    """, (stripe_event_id,))
    event = cursor.fetchone()
    conn.close()
    return event is not None

#Record the Stripe event in the database before processing it, to ensure idempotency
def save_event(stripe_event_id, event_type, object_id, error=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO stripe_events (
            stripe_event_id, 
            event_type,
            object_id, 
            processed
        )
        VALUES (?, ?, ?, ?)
    """, (stripe_event_id, event_type, object_id, 0))
    conn.commit()
    conn.close()

#Records the Stripe event as processed after successful handling, or records the error if processing failed
def mark_event_processed(stripe_event_id):
    conn = get_db_connection()

    conn.execute(
        """
        UPDATE stripe_events
        SET processed = 1,
            error = NULL
        WHERE stripe_event_id = ?
        """,
        (stripe_event_id,)
    )

    conn.commit()
    conn.close()

#Stores an error message for a Stripe event if processing failed, to allow for troubleshooting and retries
def mark_event_failed(stripe_event_id, error_message):
    conn = get_db_connection()

    conn.execute(
        """
        UPDATE stripe_events
        SET processed = 0,
            error = ?
        WHERE stripe_event_id = ?
        """,
        (error_message, stripe_event_id)
    )

    conn.commit()
    conn.close()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# The home route serves the main page where users can initiate the checkout process. 
# When the user submits the form, it: 
# creates a new order in the database, 
# retrieves the Stripe price object, 
# creates a checkout session with the specified line items and metadata, 
# updates the order with the session ID and payment intent ID, 
# and redirects the user to the Stripe-hosted checkout page.
@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        price_id = os.getenv("STRIPE_PRICE_ID")
        if not price_id:
            return "Price ID not set in environment variables", 500

        order_id = create_order()

        price_obj = stripe.Price.retrieve(price_id)

        checkout_session = stripe.checkout.Session.create(
            line_items = [
                {
                    "price": price_id,
                    "quantity": 1
                }
            ], 
            mode = "payment",
            success_url = url_for("success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url = url_for("cancel", _external=True),
            metadata = {
                "order_id": str(order_id)
            },
            payment_intent_data={
                "metadata": {
                    "order_id": str(order_id),
                    "product_name": "Baby Cardigan"
                }
            }
        )

        update_order_with_session(order_id, checkout_session.id)

        if checkout_session.payment_intent:
            update_order_with_payment_intent(order_id, checkout_session.payment_intent)

        return redirect(checkout_session.url, code=303)
    
    return render_template("index.html")

@app.route("/success")
def success():
    session_id = request.args.get("session_id")

    session = stripe.checkout.Session.retrieve(session_id)

    if session.payment_status == "paid":
        return render_template("success.html")
    else:
        return redirect(url_for("cancel"))
    
@app.route("/cancel")
def cancel():
    return render_template("cancel.html")

@app.route("/orders")
def orders():
    conn = get_db_connection()
    orders = conn.execute("SELECT * FROM orders ORDER BY id").fetchall()
    conn.close()
    return render_template("orders.html", orders=orders)

@app.route("/events")
def events():
    conn = get_db_connection()

    events = conn.execute(
        """
        SELECT * FROM stripe_events
        ORDER BY created_at DESC
        """
    ).fetchall()

    conn.close()

    return render_template("events.html", events=events)

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            endpoint_secret
        )

    except ValueError:
        return "Invalid payload", 400

    except stripe.error.SignatureVerificationError:
        return "Invalid signature", 400

    stripe_event_id = event.id
    event_type = event.type
    event_object = event.data.object
    object_id = event_object.id

    save_event(stripe_event_id, event_type, object_id)

    if event_already_processed(stripe_event_id):
        print(f"Skipping already processed event: {stripe_event_id}")
        return "Already processed", 200

    try:
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

            print(f"Order paid for Checkout Session: {stripe_session_id}")

        mark_event_processed(stripe_event_id)

    except Exception as e:
        mark_event_failed(stripe_event_id, str(e))
        print(f"Failed to process event {stripe_event_id}: {e}")
        return "Webhook processing failed", 500

    return "Success", 200

if __name__ == "__main__":
    app.run(debug=True)