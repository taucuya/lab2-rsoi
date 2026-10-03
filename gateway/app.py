from flask import Flask, request, jsonify
import requests
import uuid
import os

app = Flask(__name__)

FLIGHT_SERVICE = os.getenv("FLIGHT_SERVICE_URL", "http://flight_service:8060")
TICKET_SERVICE = os.getenv("TICKET_SERVICE_URL", "http://ticket_service:8070")
BONUS_SERVICE = os.getenv("BONUS_SERVICE_URL", "http://bonus_service:8050")


def upstream_json(resp):
    try:
        return resp.json()
    except ValueError:
        return None


@app.route("/manage/health")
def health():
    return "OK", 200


@app.route("/api/v1/flights")
def get_flights():
    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", 10, type=int)
    resp = requests.get(f"{FLIGHT_SERVICE}/flights", params={"page": page, "size": size})
    data = upstream_json(resp)
    if data is None:
        return jsonify({"message": "Flight service unavailable"}), 502
    return jsonify(data), resp.status_code


@app.route("/api/v1/tickets", methods=["GET"])
def get_tickets():
    username = request.headers.get("X-User-Name")
    if not username:
        return jsonify({"message": "X-User-Name header is required"}), 400

    resp = requests.get(f"{TICKET_SERVICE}/tickets", params={"username": username})
    tickets = upstream_json(resp)
    if tickets is None:
        return jsonify({"message": "Ticket service unavailable"}), 502

    result = []
    for t in tickets:
        flight_resp = requests.get(f"{FLIGHT_SERVICE}/flights/{t['flightNumber']}")
        flight_info = flight_resp.json() if flight_resp.status_code == 200 else {}

        result.append(
            {
                "ticketUid": t["ticketUid"],
                "flightNumber": t["flightNumber"],
                "fromAirport": flight_info.get("fromAirport", ""),
                "toAirport": flight_info.get("toAirport", ""),
                "date": flight_info.get("date", ""),
                "price": t["price"],
                "status": t["status"],
            }
        )

    return jsonify(result)


@app.route("/api/v1/tickets/<ticket_uid>", methods=["GET"])
def get_ticket(ticket_uid):
    username = request.headers.get("X-User-Name")
    if not username:
        return jsonify({"message": "X-User-Name header is required"}), 400

    resp = requests.get(f"{TICKET_SERVICE}/tickets/{ticket_uid}", params={"username": username})
    if resp.status_code == 404:
        return jsonify({"message": "Ticket not found"}), 404

    t = upstream_json(resp)
    if t is None:
        return jsonify({"message": "Ticket service unavailable"}), 502

    flight_resp = requests.get(f"{FLIGHT_SERVICE}/flights/{t['flightNumber']}")
    flight_info = flight_resp.json() if flight_resp.status_code == 200 else {}

    return jsonify(
        {
            "ticketUid": t["ticketUid"],
            "flightNumber": t["flightNumber"],
            "fromAirport": flight_info.get("fromAirport", ""),
            "toAirport": flight_info.get("toAirport", ""),
            "date": flight_info.get("date", ""),
            "price": t["price"],
            "status": t["status"],
        }
    )


@app.route("/api/v1/tickets", methods=["POST"])
def buy_ticket():
    username = request.headers.get("X-User-Name")
    if not username:
        return jsonify({"message": "X-User-Name header is required"}), 400

    data = request.json
    flight_number = data.get("flightNumber")
    price = data.get("price")
    paid_from_balance = data.get("paidFromBalance", False)

    flight_resp = requests.get(f"{FLIGHT_SERVICE}/flights/{flight_number}")
    if flight_resp.status_code == 404:
        return jsonify({"message": "Flight not found", "errors": [{"field": "flightNumber", "error": "Flight not found"}]}), 400
    if flight_resp.status_code != 200:
        return jsonify({"message": "Flight service unavailable"}), 502

    flight_info = upstream_json(flight_resp) or {}
    ticket_uid = str(uuid.uuid4())

    paid_by_bonuses = 0
    paid_by_money = price

    if paid_from_balance:
        debit_resp = requests.post(
            f"{BONUS_SERVICE}/privilege/debit",
            json={"username": username, "ticketUid": ticket_uid, "amount": price},
        )
        debit_data = upstream_json(debit_resp)
        if debit_data is None:
            return jsonify({"message": "Bonus service unavailable"}), 502
        paid_by_bonuses = debit_data["paidByBonuses"]
        paid_by_money = price - paid_by_bonuses
    else:
        bonus_amount = price // 10
        requests.post(
            f"{BONUS_SERVICE}/privilege/credit",
            json={
                "username": username,
                "ticketUid": ticket_uid,
                "amount": bonus_amount,
                "operationType": "FILL_IN_BALANCE",
            },
        )

    requests.post(
        f"{TICKET_SERVICE}/tickets",
        json={"username": username, "ticketUid": ticket_uid, "flightNumber": flight_number, "price": price},
    )

    priv_resp = requests.get(f"{BONUS_SERVICE}/privilege", params={"username": username})
    priv_data = upstream_json(priv_resp)
    if priv_data is None:
        return jsonify({"message": "Bonus service unavailable"}), 502

    return jsonify(
        {
            "ticketUid": ticket_uid,
            "flightNumber": flight_number,
            "fromAirport": flight_info.get("fromAirport", ""),
            "toAirport": flight_info.get("toAirport", ""),
            "date": flight_info.get("date", ""),
            "price": price,
            "paidByMoney": paid_by_money,
            "paidByBonuses": paid_by_bonuses,
            "status": "PAID",
            "privilege": {"balance": priv_data["balance"], "status": priv_data["status"]},
        }
    )


@app.route("/api/v1/tickets/<ticket_uid>", methods=["DELETE"])
def refund_ticket(ticket_uid):
    username = request.headers.get("X-User-Name")
    if not username:
        return jsonify({"message": "X-User-Name header is required"}), 400

    ticket_resp = requests.get(f"{TICKET_SERVICE}/tickets/{ticket_uid}", params={"username": username})
    if ticket_resp.status_code == 404:
        return jsonify({"message": "Ticket not found"}), 404

    ticket = upstream_json(ticket_resp)
    if ticket is None:
        return jsonify({"message": "Ticket service unavailable"}), 502

    if ticket["status"] == "CANCELED":
        return "", 204

    requests.patch(f"{TICKET_SERVICE}/tickets/{ticket_uid}", json={"status": "CANCELED"})

    priv_resp = requests.get(f"{BONUS_SERVICE}/privilege", params={"username": username})
    priv_data = upstream_json(priv_resp)
    if priv_data is None:
        return jsonify({"message": "Bonus service unavailable"}), 502

    fill_entry = None
    debit_entry = None
    for h in priv_data.get("history", []):
        if h["ticketUid"] == ticket_uid:
            if h["operationType"] == "FILL_IN_BALANCE":
                fill_entry = h
            elif h["operationType"] == "DEBIT_THE_ACCOUNT":
                debit_entry = h

    if debit_entry:
        requests.post(
            f"{BONUS_SERVICE}/privilege/credit",
            json={
                "username": username,
                "ticketUid": ticket_uid,
                "amount": abs(debit_entry["balanceDiff"]),
                "operationType": "FILL_IN_BALANCE",
            },
        )
    elif fill_entry:
        requests.post(
            f"{BONUS_SERVICE}/privilege/debit",
            json={"username": username, "ticketUid": ticket_uid, "amount": abs(fill_entry["balanceDiff"])},
        )

    return "", 204


@app.route("/api/v1/me")
def get_me():
    username = request.headers.get("X-User-Name")
    if not username:
        return jsonify({"message": "X-User-Name header is required"}), 400

    tickets_resp = requests.get(f"{TICKET_SERVICE}/tickets", params={"username": username})
    tickets_raw = upstream_json(tickets_resp)
    if tickets_raw is None:
        return jsonify({"message": "Ticket service unavailable"}), 502

    tickets = []
    for t in tickets_raw:
        flight_resp = requests.get(f"{FLIGHT_SERVICE}/flights/{t['flightNumber']}")
        flight_info = flight_resp.json() if flight_resp.status_code == 200 else {}
        tickets.append(
            {
                "ticketUid": t["ticketUid"],
                "flightNumber": t["flightNumber"],
                "fromAirport": flight_info.get("fromAirport", ""),
                "toAirport": flight_info.get("toAirport", ""),
                "date": flight_info.get("date", ""),
                "price": t["price"],
                "status": t["status"],
            }
        )

    priv_resp = requests.get(f"{BONUS_SERVICE}/privilege", params={"username": username})
    priv_data = upstream_json(priv_resp)
    if priv_data is None:
        return jsonify({"message": "Bonus service unavailable"}), 502

    return jsonify(
        {
            "tickets": tickets,
            "privilege": {"balance": priv_data["balance"], "status": priv_data["status"]},
        }
    )


@app.route("/api/v1/privilege")
def get_privilege():
    username = request.headers.get("X-User-Name")
    if not username:
        return jsonify({"message": "X-User-Name header is required"}), 400

    resp = requests.get(f"{BONUS_SERVICE}/privilege", params={"username": username})
    data = upstream_json(resp)
    if data is None:
        return jsonify({"message": "Bonus service unavailable"}), 502
    return jsonify(data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)