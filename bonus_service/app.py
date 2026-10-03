from flask import Flask, request, jsonify
import psycopg2
import psycopg2.extras
import os
from datetime import datetime, timezone

app = Flask(__name__)

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = "privileges"
DB_USER = os.getenv("DB_USER", "program")
DB_PASSWORD = os.getenv("DB_PASSWORD", "test")


def get_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )


def get_or_create_privilege(cur, conn, username):
    cur.execute("SELECT id, balance, status FROM privilege WHERE username = %s", (username,))
    priv = cur.fetchone()
    if not priv:
        cur.execute(
            "INSERT INTO privilege (username, status, balance) VALUES (%s, %s, %s) RETURNING id, balance, status",
            (username, "BRONZE", 0),
        )
        priv = cur.fetchone()
        conn.commit()
    return priv


@app.route("/manage/health")
def health():
    return "OK", 200


@app.route("/privilege")
def get_privilege():
    username = request.args.get("username")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    priv = get_or_create_privilege(cur, conn, username)

    cur.execute(
        """
        SELECT ph.datetime, ph.ticket_uid, ph.balance_diff, ph.operation_type
        FROM privilege_history ph
        WHERE ph.privilege_id = %s
        ORDER BY ph.datetime
        """,
        (priv["id"],),
    )
    history = cur.fetchall()
    cur.close()
    conn.close()

    history_items = []
    for h in history:
        dt = h["datetime"]
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        history_items.append(
            {
                "date": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "ticketUid": str(h["ticket_uid"]),
                "balanceDiff": h["balance_diff"],
                "operationType": h["operation_type"],
            }
        )

    return jsonify({"balance": priv["balance"], "status": priv["status"], "history": history_items})


@app.route("/privilege/debit", methods=["POST"])
def debit():
    data = request.json
    username = data["username"]
    ticket_uid = data["ticketUid"]
    amount = data["amount"]

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    priv = get_or_create_privilege(cur, conn, username)

    actual_debit = min(amount, priv["balance"])
    new_balance = priv["balance"] - actual_debit

    cur.execute("UPDATE privilege SET balance = %s WHERE id = %s", (new_balance, priv["id"]))
    cur.execute(
        """
        INSERT INTO privilege_history (privilege_id, ticket_uid, datetime, balance_diff, operation_type)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (priv["id"], ticket_uid, datetime.now(timezone.utc), -actual_debit, "DEBIT_THE_ACCOUNT"),
    )
    conn.commit()

    cur.execute("SELECT balance, status FROM privilege WHERE id = %s", (priv["id"],))
    updated = cur.fetchone()
    cur.close()
    conn.close()

    return jsonify({"paidByBonuses": actual_debit, "balance": updated["balance"], "status": updated["status"]})


@app.route("/privilege/credit", methods=["POST"])
def credit():
    data = request.json
    username = data["username"]
    ticket_uid = data["ticketUid"]
    amount = data["amount"]
    operation_type = data.get("operationType", "FILL_IN_BALANCE")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    priv = get_or_create_privilege(cur, conn, username)

    new_balance = priv["balance"] + amount

    cur.execute("UPDATE privilege SET balance = %s WHERE id = %s", (new_balance, priv["id"]))
    cur.execute(
        """
        INSERT INTO privilege_history (privilege_id, ticket_uid, datetime, balance_diff, operation_type)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (priv["id"], ticket_uid, datetime.now(timezone.utc), amount, operation_type),
    )
    conn.commit()

    cur.execute("SELECT balance, status FROM privilege WHERE id = %s", (priv["id"],))
    updated = cur.fetchone()
    cur.close()
    conn.close()

    return jsonify({"balance": updated["balance"], "status": updated["status"]})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050)
