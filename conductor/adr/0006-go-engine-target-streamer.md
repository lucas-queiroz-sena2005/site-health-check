# ADR 0006: Go Engine Architecture & Pluggable TargetStreamer

## Context
We need the Go probing engine to be 100% prepared for a distributed RabbitMQ architecture in the future, while still allowing the Go binary to function as a standalone, zero-dependency CLI tool (with local CIDR splitting) without requiring external services or daemons.

## Decision

1. **Go Channel Core Abstraction**:
   The core Go probing engine consumes targets exclusively from a native Go channel (`<-chan Target`). The probing loop (TCP connect, TLS handshake, HTTP status check) is completely decoupled from where targets originate.

2. **`TargetStreamer` Interface**:
   Target generation is abstracted behind a single interface:
   ```go
   type TargetStreamer interface {
       StreamTargets(ctx context.Context, out chan<- Target) error
   }
   ```

3. **Pluggable Implementations**:
   - `InMemSplitter`: Built-in CIDR generator package (`pkg/splitter`) used in standalone CLI mode. Expands CIDR ranges directly in RAM into the target channel with zero external daemons.
   - `RabbitMQConsumer`: AMQP consumer used in distributed control-plane mode. Listens to RabbitMQ queues and streams incoming task JSON into the exact same target channel.

## Consequences
- **Pros**: The CLI binary remains portable, fast, and self-contained. The Go codebase is completely RabbitMQ-ready without code duplication.
- **Cons**: Requires maintaining the `TargetStreamer` interface layer in Go from the outset.
