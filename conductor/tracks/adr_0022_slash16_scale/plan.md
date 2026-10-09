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

## Phase 3: Frontend Representation
- [x] Task: Write Tests for UI Data Fetching
  - [x] Write failing unit test for `HostTablePage` rendering Subrun Nodes natively
  - [x] Write failing test for on-demand fetch behavior when `[FETCH]` is clicked
- [x] Task: Implement Frontend changes
  - [x] Add Subrun Node layer to the Canonical Hierarchical Tree
  - [x] Implement `[FETCH]` button and partial data loading API calls
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)
