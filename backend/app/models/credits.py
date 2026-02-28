from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CreditAccountType(StrEnum):
    user = "user"
    node = "node"
    platform = "platform"


class CreditTransactionType(StrEnum):
    mint = "mint"
    debit = "debit"
    reward = "reward"
    transfer = "transfer"
    refund = "refund"


class CreditAccount(BaseModel):
    account_type: CreditAccountType
    account_id: str
    balance: float = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CreditTransaction(BaseModel):
    id: str = Field(default_factory=lambda: f"txn-{uuid4().hex[:12]}")
    type: CreditTransactionType
    amount: float = Field(gt=0)
    from_account_type: CreditAccountType | None = None
    from_account_id: str | None = None
    to_account_type: CreditAccountType | None = None
    to_account_id: str | None = None
    reference_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class CreditMintRequest(BaseModel):
    account_type: CreditAccountType
    account_id: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=1_000_000)
    reason: str = Field(default="admin_mint", min_length=1, max_length=200)


class CreditSpendRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=1_000_000)
    reference_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="manual_spend", min_length=1, max_length=200)


class CreditRewardRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=1_000_000)
    reference_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="compute_reward", min_length=1, max_length=200)


class CreditTransferRequest(BaseModel):
    from_account_type: CreditAccountType
    from_account_id: str = Field(min_length=1, max_length=200)
    to_account_type: CreditAccountType
    to_account_id: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=1_000_000)
    reference_id: str = Field(default="", max_length=200)
    reason: str = Field(default="transfer", min_length=1, max_length=200)


class CreditBalanceResponse(BaseModel):
    account: CreditAccount
    recent_transactions: list[CreditTransaction] = Field(default_factory=list)


class CreditTransactionListResponse(BaseModel):
    items: list[CreditTransaction] = Field(default_factory=list)
