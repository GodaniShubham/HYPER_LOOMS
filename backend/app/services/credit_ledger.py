from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

from app.models.credits import (
    CreditAccount,
    CreditAccountType,
    CreditTransaction,
    CreditTransactionType,
)
from app.models.job import JobConfig


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CreditLedger:
    MODEL_SIZE_REGEX = re.compile(r"(?P<size>\d+)(?:\.\d+)?b", re.IGNORECASE)
    PLATFORM_ACCOUNT_ID = "platform-reserve"

    def __init__(self, bootstrap_user_credits: float = 1000.0) -> None:
        self._lock = asyncio.Lock()
        self._accounts: dict[tuple[CreditAccountType, str], CreditAccount] = {}
        self._transactions: list[CreditTransaction] = []
        self._idempotency: dict[str, CreditTransaction] = {}
        self._bootstrap_user_credits = max(0.0, bootstrap_user_credits)

    async def estimate_job_cost(self, config: JobConfig) -> float:
        model_name = config.model.lower()
        size_match = self.MODEL_SIZE_REGEX.search(model_name)
        model_size_hint = float(size_match.group("size")) if size_match else 13.0
        token_factor = max(0.5, min(4.0, config.max_tokens / 1024))
        replica_factor = max(1, config.replicas)
        base = 0.35 + (model_size_hint * 0.028) + (token_factor * 0.22)
        return round(max(0.25, base * replica_factor), 4)

    async def get_account(
        self,
        account_type: CreditAccountType,
        account_id: str,
        *,
        create_if_missing: bool = True,
    ) -> CreditAccount:
        key = (account_type, account_id)
        async with self._lock:
            account = self._accounts.get(key)
            if account:
                return account
            if not create_if_missing:
                raise KeyError(f"account_not_found: {account_type}:{account_id}")
            seeded = self._bootstrap_user_credits if account_type == CreditAccountType.user else 0.0
            account = CreditAccount(account_type=account_type, account_id=account_id, balance=seeded)
            self._accounts[key] = account
            return account

    async def mint(
        self,
        account_type: CreditAccountType,
        account_id: str,
        amount: float,
        *,
        reason: str = "mint",
        reference_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> CreditTransaction:
        if amount <= 0:
            raise ValueError("mint_amount_must_be_positive")
        async with self._lock:
            if idempotency_key and idempotency_key in self._idempotency:
                return self._idempotency[idempotency_key]
            account = self._accounts.get((account_type, account_id))
            if not account:
                seed = self._bootstrap_user_credits if account_type == CreditAccountType.user else 0.0
                account = CreditAccount(account_type=account_type, account_id=account_id, balance=seed)
            account = account.model_copy(update={"balance": round(account.balance + amount, 4), "updated_at": utc_now()})
            self._accounts[(account_type, account_id)] = account

            txn = CreditTransaction(
                type=CreditTransactionType.mint,
                amount=round(amount, 4),
                to_account_type=account_type,
                to_account_id=account_id,
                reference_id=reference_id,
                metadata={"reason": reason},
            )
            self._transactions.append(txn)
            if idempotency_key:
                self._idempotency[idempotency_key] = txn
            return txn

    async def transfer(
        self,
        *,
        from_account_type: CreditAccountType,
        from_account_id: str,
        to_account_type: CreditAccountType,
        to_account_id: str,
        amount: float,
        txn_type: CreditTransactionType,
        reason: str,
        reference_id: str | None = None,
        idempotency_key: str | None = None,
        allow_negative_source: bool = False,
    ) -> CreditTransaction:
        if amount <= 0:
            raise ValueError("transfer_amount_must_be_positive")
        async with self._lock:
            if idempotency_key and idempotency_key in self._idempotency:
                return self._idempotency[idempotency_key]

            source = self._accounts.get((from_account_type, from_account_id))
            if not source:
                seed = self._bootstrap_user_credits if from_account_type == CreditAccountType.user else 0.0
                source = CreditAccount(account_type=from_account_type, account_id=from_account_id, balance=seed)
            target = self._accounts.get((to_account_type, to_account_id))
            if not target:
                seed = self._bootstrap_user_credits if to_account_type == CreditAccountType.user else 0.0
                target = CreditAccount(account_type=to_account_type, account_id=to_account_id, balance=seed)

            next_source_balance = round(source.balance - amount, 4)
            if not allow_negative_source and next_source_balance < 0:
                raise ValueError("insufficient_credits")

            source = source.model_copy(update={"balance": max(0.0, next_source_balance), "updated_at": utc_now()})
            target = target.model_copy(update={"balance": round(target.balance + amount, 4), "updated_at": utc_now()})
            self._accounts[(from_account_type, from_account_id)] = source
            self._accounts[(to_account_type, to_account_id)] = target

            txn = CreditTransaction(
                type=txn_type,
                amount=round(amount, 4),
                from_account_type=from_account_type,
                from_account_id=from_account_id,
                to_account_type=to_account_type,
                to_account_id=to_account_id,
                reference_id=reference_id,
                metadata={"reason": reason},
            )
            self._transactions.append(txn)
            if idempotency_key:
                self._idempotency[idempotency_key] = txn
            return txn

    async def charge_user_for_job(self, user_id: str, job_id: str, amount: float) -> CreditTransaction:
        return await self.transfer(
            from_account_type=CreditAccountType.user,
            from_account_id=user_id,
            to_account_type=CreditAccountType.platform,
            to_account_id=self.PLATFORM_ACCOUNT_ID,
            amount=amount,
            txn_type=CreditTransactionType.debit,
            reason="job_charge",
            reference_id=job_id,
            idempotency_key=f"charge:{job_id}:{user_id}",
        )

    async def reward_node(self, node_id: str, job_id: str, amount: float, *, reason: str = "compute_reward") -> CreditTransaction:
        return await self.transfer(
            from_account_type=CreditAccountType.platform,
            from_account_id=self.PLATFORM_ACCOUNT_ID,
            to_account_type=CreditAccountType.node,
            to_account_id=node_id,
            amount=amount,
            txn_type=CreditTransactionType.reward,
            reason=reason,
            reference_id=job_id,
            idempotency_key=f"reward:{job_id}:{node_id}:{reason}",
            allow_negative_source=True,
        )

    async def refund_user(self, user_id: str, job_id: str, amount: float) -> CreditTransaction:
        return await self.transfer(
            from_account_type=CreditAccountType.platform,
            from_account_id=self.PLATFORM_ACCOUNT_ID,
            to_account_type=CreditAccountType.user,
            to_account_id=user_id,
            amount=amount,
            txn_type=CreditTransactionType.refund,
            reason="job_refund",
            reference_id=job_id,
            idempotency_key=f"refund:{job_id}:{user_id}",
            allow_negative_source=True,
        )

    async def list_transactions(
        self,
        *,
        account_type: CreditAccountType | None = None,
        account_id: str | None = None,
        limit: int = 100,
    ) -> list[CreditTransaction]:
        size = max(1, min(500, limit))
        async with self._lock:
            items = list(self._transactions)
        items.reverse()
        if account_type and account_id:
            key_type = account_type
            key_id = account_id
            items = [
                item
                for item in items
                if (item.from_account_type == key_type and item.from_account_id == key_id)
                or (item.to_account_type == key_type and item.to_account_id == key_id)
            ]
        return items[:size]
