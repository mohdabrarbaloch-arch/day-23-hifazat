"""Seed script — creates the demo user, a warm account with 45 days of
realistic history (replayed through the anomaly engine so the profile is
genuinely learned), and drop-in fraud story transactions.

Run: python -m app.seed
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from . import models
from .database import Base, SessionLocal, engine
from .routers.transactions import process_transaction
from .security import hash_password

DEMO_EMAIL = "demo@hifazat.pk"
DEMO_PASSWORD = "demo12345"

# (merchant, category, city) patterns for the demo's normal life.
EVERYDAY = [
    ("Imtiaz Super Store", "groceries", "Karachi"),
    ("K-Electric", "utilities", "Karachi"),
    ("Jazz Cash", "mobile", "Karachi"),
    ("Careem", "transport", "Karachi"),
    ("Al-Falah Restaurant", "dining", "Karachi"),
    ("Lucky One Mall", "shopping", "Karachi"),
    ("Shell Fuel Station", "fuel", "Karachi"),
    ("NetSol ISP", "utilities", "Karachi"),
    ("Sehat Pharmacy", "health", "Karachi"),
    ("Daraz.pk", "shopping", "Karachi"),
]

# Fraud story, in chronological order (oldest first). The last two entries are
# the actual incident: a normal Karachi purchase, then a large Lahore payment
# an hour later — physically impossible, so the engine must flag it.
# (hours_ago, amount, merchant, category, city, country)
STORY = [
    (14 * 24, 4_800.0, "Careem", "transport", "Karachi", "Pakistan"),
    (9 * 24, 12_200.0, "Lucky One Mall", "shopping", "Karachi", "Pakistan"),
    (7 * 24, 6_500.0, "Imtiaz Super Store", "groceries", "Karachi", "Pakistan"),
    (3 * 24, 32_000.0, "Ali Traders", "other", "Lahore", "Pakistan"),
    (5, 2_200.0, "Imtiaz Super Store", "groceries", "Karachi", "Pakistan"),
    (4, 248_000.0, "Runner Imports", "other", "Lahore", "Pakistan"),
]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.scalar(select(models.User).where(models.User.email == DEMO_EMAIL))
        if existing is not None:
            print("Demo user already exists — skipping (delete hifazat.db to reseed).")
            return

        user = models.User(
            email=DEMO_EMAIL,
            name="Demo User",
            password_hash=hash_password(DEMO_PASSWORD),
            is_demo=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        account = models.Account(
            user_id=user.id,
            name="HBL Current Account",
            account_type="checking",
            bank="HBL",
            currency="PKR",
            balance=620_000.0,
            home_city="Karachi",
            home_country="Pakistan",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        # Build 45 days of routine history as data, then replay it through the
        # engine exactly once — duplicating nothing, learning a real profile.
        now = datetime.now(UTC)
        seed_start = now - timedelta(days=45)
        history = []
        for day_offset in range(45):
            t = seed_start + timedelta(days=day_offset, hours=9 + (day_offset % 8))
            merchant, category, city = EVERYDAY[day_offset % len(EVERYDAY)]
            amount = round(800.0 + ((day_offset * 37) % 4200), 2)
            channel = "card" if day_offset % 3 else "bank"
            history.append(
                {
                    "amount": amount,
                    "category": category,
                    "merchant": merchant,
                    "city": city,
                    "country": "Pakistan",
                    "channel": channel,
                    "occurred_at": t,
                }
            )

        for tx_data in history:
            process_transaction(db, account, tx_data)
            db.refresh(account)

        # Fraud story, replayed oldest-first so every gap is a real elapsed gap.
        now2 = datetime.now(UTC)
        for hours_ago, amount, merchant, category, city, country in STORY:
            occurred = now2 - timedelta(hours=hours_ago)
            process_transaction(
                db,
                account,
                {
                    "amount": amount,
                    "merchant": merchant,
                    "category": category,
                    "city": city,
                    "country": country,
                    "channel": "card",
                    "occurred_at": occurred,
                },
            )
            db.refresh(account)

        db.commit()
        print(f"Seeded demo user: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print(f"Account: {account.name} — balance Rs {account.balance:,.0f}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
