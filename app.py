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

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

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

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError as e:
        return "Invalid signature", 400 
    
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        mark_order_paid_by_session(session.id)

        stripe_session_id = session.id
        stripe_payment_intent_id = session.payment_intent

        if stripe_payment_intent_id:
            update_payment_intent_by_session(session.id, stripe_payment_intent_id)

        print(f"Checkout session completed: {session.id}")

    return "Webhook received", 200

if __name__ == "__main__":
    app.run(debug=True)