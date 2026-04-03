from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class AccountType(str, Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class AccountSubtype(str, Enum):
    # Assets
    CASH = "cash"
    BANK = "bank"
    ACCOUNTS_RECEIVABLE = "accounts_receivable"
    PREPAID = "prepaid"
    FIXED_ASSET = "fixed_asset"
    # Liabilities
    ACCOUNTS_PAYABLE = "accounts_payable"
    ACCRUED_LIABILITY = "accrued_liability"
    SECURITY_DEPOSIT = "security_deposit"
    # Equity
    RETAINED_EARNINGS = "retained_earnings"
    OWNER_EQUITY = "owner_equity"
    # Revenue
    RENT_INCOME = "rent_income"
    MANAGEMENT_FEE = "management_fee"
    LATE_FEE = "late_fee"
    OTHER_INCOME = "other_income"
    # Expense
    MAINTENANCE = "maintenance"
    UTILITIES = "utilities"
    INSURANCE = "insurance"
    HOA = "hoa"
    MORTGAGE = "mortgage"
    TAX = "tax"
    MANAGEMENT_EXPENSE = "management_expense"
    CONTRACTOR = "contractor"
    ADVERTISING = "advertising"
    OTHER_EXPENSE = "other_expense"


class AccountDB(BaseModel):
    """Chart of Accounts entry."""

    id: Optional[str] = Field(None, alias="_id")
    code: str
    name: str
    account_type: AccountType
    subtype: AccountSubtype
    parent_id: Optional[str] = None
    property_id: Optional[str] = None  # None = company-level
    description: Optional[str] = None
    is_active: bool = True
    is_system: bool = False  # System accounts cannot be deleted
    normal_balance: str = "debit"  # "debit" or "credit"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class JournalLine(BaseModel):
    """A single debit or credit line in a journal entry."""

    account_id: str
    account_code: str
    account_name: str
    debit: float = 0.0
    credit: float = 0.0
    description: Optional[str] = None
    property_id: Optional[str] = None


class JournalEntryDB(BaseModel):
    """Double-entry journal entry. Sum(debits) must == Sum(credits)."""

    id: Optional[str] = Field(None, alias="_id")
    entry_number: str
    date: date
    description: str
    entry_type: str  # rent, invoice, payment, expense, adjustment, opening
    lines: List[JournalLine]
    reference_id: Optional[str] = None  # invoice_id, work_order_id, etc.
    reference_type: Optional[str] = None  # "invoice", "work_order", "payment"
    property_id: Optional[str] = None
    is_voided: bool = False
    void_reason: Optional[str] = None
    created_by: str
    approved_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True

    def validate_balance(self) -> bool:
        total_debit = sum(line.debit for line in self.lines)
        total_credit = sum(line.credit for line in self.lines)
        return abs(total_debit - total_credit) < 0.01


class LedgerBalanceDB(BaseModel):
    """Materialized balance per account per period for fast reporting."""

    id: Optional[str] = Field(None, alias="_id")
    account_id: str
    account_code: str
    property_id: Optional[str] = None
    period_year: int
    period_month: int
    opening_balance: float = 0.0
    total_debits: float = 0.0
    total_credits: float = 0.0
    closing_balance: float = 0.0
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
