from flask import Flask, request, jsonify
import psycopg2
import psycopg2.extras
import os

app = Flask(__name__)

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = "flights"
DB_USER = os.getenv("DB_USER", "program")
DB_PASSWORD = os.getenv("DB_PASSWORD", "test")


def get_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )


@app.route("/manage/health")
def health():
    return "OK", 200


@app.route("/flights")
def get_flights():
    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", 10, type=int)

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT COUNT(*) FROM flight")
    total = cur.fetchone()["count"]

    offset = max(0, (page - 1)) * size
    cur.execute(
        """
        SELECT f.flight_number, f.datetime, f.price,
               fa.city || ' ' || fa.name as from_airport,
               ta.city || ' ' || ta.name as to_airport
        FROM flight f
        JOIN airport fa ON f.from_airport_id = fa.id
        JOIN airport ta ON f.to_airport_id = ta.id
        ORDER BY f.id
        LIMIT %s OFFSET %s
        """,
        (size, offset),
    )
    flights = cur.fetchall()
    cur.close()
    conn.close()

    items = []
    for f in flights:
        items.append(
            {
                "flightNumber": f["flight_number"],
                "fromAirport": f["from_airport"],
                "toAirport": f["to_airport"],
                "date": f["datetime"].strftime("%Y-%m-%d %H:%M"),
                "price": f["price"],
            }
        )

    return jsonify({"page": page, "pageSize": size, "totalElements": total, "items": items})


@app.route("/flights/<flight_number>")
def get_flight(flight_number):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        SELECT f.flight_number, f.datetime, f.price,
               fa.city || ' ' || fa.name as from_airport,
               ta.city || ' ' || ta.name as to_airport
        FROM flight f
        JOIN airport fa ON f.from_airport_id = fa.id
        JOIN airport ta ON f.to_airport_id = ta.id
        WHERE f.flight_number = %s
        """,
        (flight_number,),
    )
    flight = cur.fetchone()
    cur.close()
    conn.close()

    if not flight:
        return jsonify({"message": "Flight not found"}), 404

    return jsonify(
        {
            "flightNumber": flight["flight_number"],
            "fromAirport": flight["from_airport"],
            "toAirport": flight["to_airport"],
            "date": flight["datetime"].strftime("%Y-%m-%d %H:%M"),
            "price": flight["price"],
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8060)
