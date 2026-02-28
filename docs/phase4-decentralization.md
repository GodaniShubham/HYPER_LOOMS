# ComputeFabric Phase 4 Vision

## M) Peer-to-Peer Orchestration Model

### Architecture Diagram (Text)
```text
                        +----------------------------+
                        |    User / App / SDKs       |
                        +-------------+--------------+
                                      |
                         signed JobIntent + budget
                                      |
                   +------------------v------------------+
                   |      Edge Peer (any trusted node)   |
                   |  - validates intent + credits proof  |
                   |  - gossips job intent to swarm       |
                   +------------------+------------------+
                                      |
                  gossip membership + job proposals
                                      |
        +-----------------------------+-----------------------------+
        |               Peer Mesh (no central coordinator)         |
        |  - gossip discovery                                      |
        |  - deterministic rendezvous candidate set                |
        |  - quorum vote / consensus commit                        |
        +-----------+-------------------+-------------------+-------+
                    |                   |                   |
           +--------v------+   +--------v------+   +--------v------+
           | Compute Peer A|   | Compute Peer B|   | Compute Peer C|
           | worker/validator   worker/validator    worker/validator|
           +--------+------+   +--------+------+   +--------+------+
                    |                   |                   |
                    +--------- partial outputs + proofs ----+
                                      |
                               verification quorum
                                      |
                            final merged response + receipts
```

### Core Protocols
- `Gossip Membership`: anti-entropy gossip with peer liveness, trust, load, and model cache metadata.
- `Deterministic Candidate Selection`: rendezvous hashing over `(job_id, peer_id)` to generate stable assignment set.
- `Consensus Commit`: quorum of validators signs one assignment decision and execution receipt.
- `Receipt Chain`: each completed job emits signed receipts (`assignment`, `execution`, `verification`, `credit settlement`).

### Sequence Flow
1. Client submits `JobIntent` (prompt hash, model, replicas, region, max budget).
2. Entry peer validates budget/nonce and gossips intent.
3. Peers independently compute candidate set using deterministic hashing.
4. Validators exchange proposals and finalize assignment by quorum.
5. Workers execute shards/replicas and stream partial outputs + latency proofs.
6. Verification quorum runs semantic + majority validation.
7. Final output, quorum certificate, and credit settlements are published.

### Future Roadmap
1. **Stage 1 (Now)**: in-process P2P simulation service (`/api/v1/p2p/*`) + deterministic assignment.
2. **Stage 2**: standalone peer daemon with signed gossip + persistent Raft log per region.
3. **Stage 3**: cross-region federation, multi-quorum verification, and dispute resolution.
4. **Stage 4**: coordinatorless execution path with client-routable job intents and cryptographic receipts.

## N) Incentive / Credit System

### Simple Economic Model
- **Users spend credits** based on estimated workload cost:
  - `cost = f(model_size, max_tokens, replicas, provider_factor)`.
- **Nodes earn credits** for successful replica execution:
  - base reward per replica + majority/verification bonus.
- **Refund rule**:
  - failed jobs automatically refund user credits.
- **Platform reserve**:
  - funds node rewards and can be topped up by admin minting.

### Ledger Principles
- Double-entry style transfers: user -> platform (spend), platform -> node (reward).
- Idempotency keys for all automated settlement actions.
- Immutable transaction history with references (`job_id`, `node_id`, reason).

### API Design (Implemented)
- `GET /api/v1/credits/accounts/{account_type}/{account_id}`: balance + recent transactions.
- `GET /api/v1/credits/transactions/list`: transaction stream with optional account filters.
- `POST /api/v1/credits/mint` (admin): mint to any account.
- `POST /api/v1/credits/spend`: manual debit from user to platform.
- `POST /api/v1/credits/reward` (admin): reward node manually.
- `POST /api/v1/credits/transfer` (admin): generic transfer.

### Job Lifecycle Settlement (Implemented)
- On submit: estimated credits are charged from `owner_id`.
- On successful completion: participating nodes receive rewards.
- On failure: charged credits are refunded to `owner_id`.
