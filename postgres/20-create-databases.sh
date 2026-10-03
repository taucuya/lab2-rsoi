#!/usr/bin/env bash
set -e

export VARIANT="v1"
export SCRIPT_PATH=/docker-entrypoint-initdb.d/
export PGPASSWORD=postgres
psql -f "$SCRIPT_PATH/scripts/db-$VARIANT.sql"

psql -d flights -U postgres -c "
CREATE TABLE IF NOT EXISTS airport (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(255),
    city    VARCHAR(255),
    country VARCHAR(255)
);
CREATE TABLE IF NOT EXISTS flight (
    id              SERIAL PRIMARY KEY,
    flight_number   VARCHAR(20)              NOT NULL,
    datetime        TIMESTAMP WITH TIME ZONE NOT NULL,
    from_airport_id INT REFERENCES airport (id),
    to_airport_id   INT REFERENCES airport (id),
    price           INT                      NOT NULL
);
INSERT INTO airport (id, name, city, country) VALUES (1, 'Шереметьево', 'Москва', 'Россия'), (2, 'Пулково', 'Санкт-Петербург', 'Россия');
INSERT INTO flight (id, flight_number, datetime, from_airport_id, to_airport_id, price) VALUES (1, 'AFL031', '2021-10-08 20:00:00+00', 2, 1, 1500);
GRANT ALL ON ALL TABLES IN SCHEMA public TO program;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO program;
"

psql -d tickets -U postgres -c "
CREATE TABLE IF NOT EXISTS ticket (
    id            SERIAL PRIMARY KEY,
    ticket_uid    uuid UNIQUE NOT NULL,
    username      VARCHAR(80) NOT NULL,
    flight_number VARCHAR(20) NOT NULL,
    price         INT         NOT NULL,
    status        VARCHAR(20) NOT NULL
        CHECK (status IN ('PAID', 'CANCELED'))
);
GRANT ALL ON ALL TABLES IN SCHEMA public TO program;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO program;
"

psql -d privileges -U postgres -c "
CREATE TABLE IF NOT EXISTS privilege (
    id       SERIAL PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    status   VARCHAR(80) NOT NULL DEFAULT 'BRONZE'
        CHECK (status IN ('BRONZE', 'SILVER', 'GOLD')),
    balance  INT
);
CREATE TABLE IF NOT EXISTS privilege_history (
    id             SERIAL PRIMARY KEY,
    privilege_id   INT REFERENCES privilege (id),
    ticket_uid     uuid        NOT NULL,
    datetime       TIMESTAMP   NOT NULL,
    balance_diff   INT         NOT NULL,
    operation_type VARCHAR(20) NOT NULL
        CHECK (operation_type IN ('FILL_IN_BALANCE', 'DEBIT_THE_ACCOUNT'))
);
GRANT ALL ON ALL TABLES IN SCHEMA public TO program;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO program;
"
