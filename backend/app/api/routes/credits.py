from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_credit_ledger
from app.core.security import require_admin_api_key
from app.models.credits import (
    CreditAccountType,
    CreditBalanceResponse,
    CreditMintRequest,
    CreditRewardRequest,
    CreditSpendRequest,
    CreditTransactionListResponse,
    CreditTransactionType,
    CreditTransferRequest,
)
from app.services.credit_ledger import CreditLedger

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get("/accounts/{account_type}/{account_id}", response_model=CreditBalanceResponse)
async def account_balance(
    account_type: CreditAccountType,
    account_id: str,
    ledger: CreditLedger = Depends(get_credit_ledger),
) -> CreditBalanceResponse:
    account = await ledger.get_account(account_type, account_id, create_if_missing=True)
    recent = await ledger.list_transactions(account_type=account_type, account_id=account_id, limit=50)
    return CreditBalanceResponse(account=account, recent_transactions=recent)


@router.get("/transactions/list", response_model=CreditTransactionListResponse)
async def list_transactions(
    account_type: CreditAccountType | None = Query(default=None),
    account_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    ledger: CreditLedger = Depends(get_credit_ledger),
) -> CreditTransactionListResponse:
    if (account_type is None) ^ (account_id is None):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="account_type and account_id must be used together")
    return CreditTransactionListResponse(
        items=await ledger.list_transactions(account_type=account_type, account_id=account_id, limit=limit)
    )


@router.post("/mint", dependencies=[Depends(require_admin_api_key)])
async def mint_credits(
    payload: CreditMintRequest,
    ledger: CreditLedger = Depends(get_credit_ledger),
) -> dict:
    txn = await ledger.mint(
        account_type=payload.account_type,
        account_id=payload.account_id,
        amount=payload.amount,
        reason=payload.reason,
        reference_id=f"mint:{payload.account_type}:{payload.account_id}",
    )
    return {"transaction": txn}


@router.post("/spend")
async def spend_credits(
    payload: CreditSpendRequest,
    ledger: CreditLedger = Depends(get_credit_ledger),
) -> dict:
    try:
        txn = await ledger.transfer(
            from_account_type=CreditAccountType.user,
            from_account_id=payload.user_id,
            to_account_type=CreditAccountType.platform,
            to_account_id=ledger.PLATFORM_ACCOUNT_ID,
            amount=payload.amount,
            txn_type=CreditTransactionType.debit,
            reason=payload.reason,
            reference_id=payload.reference_id,
            idempotency_key=f"manual-spend:{payload.reference_id}:{payload.user_id}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)) from exc
    return {"transaction": txn}


@router.post("/reward", dependencies=[Depends(require_admin_api_key)])
async def reward_credits(
    payload: CreditRewardRequest,
    ledger: CreditLedger = Depends(get_credit_ledger),
) -> dict:
    txn = await ledger.reward_node(payload.node_id, payload.reference_id, payload.amount, reason=payload.reason)
    return {"transaction": txn}


@router.post("/transfer", dependencies=[Depends(require_admin_api_key)])
async def transfer_credits(
    payload: CreditTransferRequest,
    ledger: CreditLedger = Depends(get_credit_ledger),
) -> dict:
    try:
        txn = await ledger.transfer(
            from_account_type=payload.from_account_type,
            from_account_id=payload.from_account_id,
            to_account_type=payload.to_account_type,
            to_account_id=payload.to_account_id,
            amount=payload.amount,
            txn_type=CreditTransactionType.transfer,
            reason=payload.reason,
            reference_id=payload.reference_id or None,
            idempotency_key=f"manual-transfer:{payload.reference_id}:{payload.from_account_type}:{payload.from_account_id}",
            allow_negative_source=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"transaction": txn}
