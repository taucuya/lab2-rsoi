from flask import Flask, request, jsonify
import psycopg2
import psycopg2.extras
import os

app = Flask(__name__)

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = "tickets"
DB_USER = os.getenv("DB_USER", "program")
DB_PASSWORD = os.getenv("DB_PASSWORD", "test")


def get_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )


@app.route("/manage/health")
def health():
    return "OK", 200


@app.route("/tickets")
def get_tickets():
    username = request.args.get("username")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT ticket_uid, flight_number, price, status FROM ticket WHERE username = %s",
        (username,),
    )
    tickets = cur.fetchall()
    cur.close()
    conn.close()

    result = []
    for t in tickets:
        result.append(
            {
                "ticketUid": str(t["ticket_uid"]),
                "flightNumber": t["flight_number"],
                "price": t["price"],
                "status": t["status"],
            }
        )
    return jsonify(result)


@app.route("/tickets/<ticket_uid>")
def get_ticket(ticket_uid):
    username = request.args.get("username")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT ticket_uid, flight_number, price, status FROM ticket WHERE ticket_uid = %s AND username = %s",
        (ticket_uid, username),
    )
    ticket = cur.fetchone()
    cur.close()
    conn.close()

    if not ticket:
        return jsonify({"message": "Ticket not found"}), 404

    return jsonify(
        {
            "ticketUid": str(ticket["ticket_uid"]),
            "flightNumber": ticket["flight_number"],
            "price": ticket["price"],
            "status": ticket["status"],
        }
    )


@app.route("/tickets", methods=["POST"])
def create_ticket():
    data = request.json
    username = data["username"]
    ticket_uid = data["ticketUid"]
    flight_number = data["flightNumber"]
    price = data["price"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ticket (ticket_uid, username, flight_number, price, status) VALUES (%s, %s, %s, %s, %s)",
        (ticket_uid, username, flight_number, price, "PAID"),
    )
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"ticketUid": ticket_uid}), 201


@app.route("/tickets/<ticket_uid>", methods=["PATCH"])
def update_ticket(ticket_uid):
    data = request.json
    status = data.get("status", "CANCELED")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE ticket SET status = %s WHERE ticket_uid = %s", (status, ticket_uid))
    conn.commit()
    cur.close()
    conn.close()

    return "", 204


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8070)
