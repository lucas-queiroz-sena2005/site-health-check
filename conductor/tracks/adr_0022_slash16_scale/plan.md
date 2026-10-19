# Implementation Plan: ADR 0022 - Slash16 Scale Strategy

## Phase 1: Database Schema & API Contract
- [x] Task: Write Tests for DB and API changes
  - [x] Write failing test for `HostState` accepting `subrun_id`
  - [x] Write failing test for API fetching by `run_id` + `subrun_id`
- [x] Task: Implement DB and API changes
  - [x] Add `subrun_id` column to `HostState` schema
  - [x] Update API routers to accept/filter by `subrun_id`
- [x] Task: Phase Verification & Checkpoint [checkpoint: e195cd2]

## Phase 2: Engine Architecture (Memory & Scale)
- [x] Task: Write Tests for Engine Generation & Memory
  - [x] Write failing test for round-robin target generator
  - [x] Write failing test to verify `asyncio.Queue` respects maxsize=1000 bounds
- [x] Task: Implement Engine changes
  - [x] Implement round-robin logic for interleaving `/24` target blocks
  - [x] Refactor engine loop to use bounded queue
- [x] Task: Phase Verification & Checkpoint [checkpoint: 44acc69]

## Phase 3: Frontend Representation (Cancelled / Stepped Back) [checkpoint: 3c21e76]
> [!NOTE]
> Frontend changes to the table were stepped back per user decision and reverted in commit `3c21e76`.

- [x] Task: Step back and revert frontend table changes [checkpoint: 3c21e76]
