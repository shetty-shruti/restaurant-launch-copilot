"""Kafka consumer for inspections.new (weeks 5 to 6).

Upserts new restaurant inspection results into Postgres. Idempotent on
(city, restaurant id, inspection date, violation code); publishes inspections.indexed and
sends failures to inspections.dlq.
"""


def main() -> None:
    raise NotImplementedError("Weeks 5 to 6")


if __name__ == "__main__":
    main()
