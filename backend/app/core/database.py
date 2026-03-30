from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING, DESCENDING, TEXT
from app.core.config import settings
import structlog

log = structlog.get_logger()

client: AsyncIOMotorClient = None
db: AsyncIOMotorDatabase = None


async def connect_db():
    global client, db
    log.info("Connecting to MongoDB", url=settings.MONGODB_URL[:30] + "...")
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB]
    await create_indexes()
    log.info("MongoDB connected", database=settings.MONGODB_DB)


async def close_db():
    global client
    if client:
        client.close()
        log.info("MongoDB connection closed")


def get_db() -> AsyncIOMotorDatabase:
    return db


async def create_indexes():
    """Create all MongoDB indexes for performance."""
    # Users
    await db.users.create_indexes([
        IndexModel([("email", ASCENDING)], unique=True),
        IndexModel([("google_id", ASCENDING)], unique=True, sparse=True),
        IndexModel([("role", ASCENDING)]),
    ])

    # Properties
    await db.properties.create_indexes([
        IndexModel([("address.city", ASCENDING), ("address.state", ASCENDING)]),
        IndexModel([("property_type", ASCENDING)]),
        IndexModel([("status", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
        IndexModel([("name", TEXT), ("address.street", TEXT)]),
    ])

    # Ownerships (join collection)
    await db.ownerships.create_indexes([
        IndexModel([("owner_id", ASCENDING), ("property_id", ASCENDING)], unique=True),
        IndexModel([("owner_id", ASCENDING)]),
        IndexModel([("property_id", ASCENDING)]),
    ])

    # Tenants
    await db.tenants.create_indexes([
        IndexModel([("email", ASCENDING)]),
        IndexModel([("property_id", ASCENDING)]),
        IndexModel([("unit_id", ASCENDING)]),
        IndexModel([("lease_end_date", ASCENDING)]),
    ])

    # Accounting: Chart of Accounts
    await db.accounts.create_indexes([
        IndexModel([("code", ASCENDING)], unique=True),
        IndexModel([("account_type", ASCENDING)]),
        IndexModel([("parent_id", ASCENDING)]),
    ])

    # Journal Entries
    await db.journal_entries.create_indexes([
        IndexModel([("date", DESCENDING)]),
        IndexModel([("property_id", ASCENDING), ("date", DESCENDING)]),
        IndexModel([("reference_id", ASCENDING)]),
        IndexModel([("entry_type", ASCENDING)]),
        IndexModel([("lines.account_id", ASCENDING)]),
    ])

    # Invoices
    await db.invoices.create_indexes([
        IndexModel([("owner_id", ASCENDING), ("status", ASCENDING)]),
        IndexModel([("property_id", ASCENDING)]),
        IndexModel([("due_date", ASCENDING)]),
        IndexModel([("invoice_number", ASCENDING)], unique=True),
        IndexModel([("status", ASCENDING)]),
    ])

    # Payments
    await db.payments.create_indexes([
        IndexModel([("invoice_id", ASCENDING)]),
        IndexModel([("owner_id", ASCENDING)]),
        IndexModel([("payment_date", DESCENDING)]),
    ])

    # Work Orders
    await db.work_orders.create_indexes([
        IndexModel([("property_id", ASCENDING), ("status", ASCENDING)]),
        IndexModel([("assigned_vendor_id", ASCENDING)]),
        IndexModel([("priority", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
        IndexModel([("description", TEXT), ("title", TEXT)]),
    ])

    # Vendors
    await db.vendors.create_indexes([
        IndexModel([("name", ASCENDING)]),
        IndexModel([("trade_specialties", ASCENDING)]),
        IndexModel([("status", ASCENDING)]),
        IndexModel([("name", TEXT)]),
    ])

    # Documents
    await db.documents.create_indexes([
        IndexModel([("property_id", ASCENDING)]),
        IndexModel([("owner_id", ASCENDING)]),
        IndexModel([("category", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
        IndexModel([("name", TEXT), ("ai_summary", TEXT), ("tags", TEXT)]),
    ])

    # Notifications
    await db.notifications.create_indexes([
        IndexModel([("user_id", ASCENDING), ("read", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
        IndexModel([("type", ASCENDING)]),
    ])

    log.info("MongoDB indexes created")
