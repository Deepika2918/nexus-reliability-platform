# NEXUS Engineering Challenge — Written Account

## 1. Scope

This implementation focuses on the core reliability problems of NEXUS.

Implemented:

- Persistent storage of accepted work using SQLite.
- Work dispatch from the platform to local workers.
- Bounded retry behaviour for failed work.
- Visible failed/dead-letter state after retry limits are reached.
- Duplicate work detection and idempotent handling.
- Worker health tracking and bounded worker recovery.
- Event recording for work, worker and operator activity.
- Local operator dashboard.
- Local failure simulation for demonstrating recovery behaviour.
- Basic release management and rollback workflow.

The project runs entirely on one machine and does not require cloud services or AI/model calls at runtime.

I deliberately focused on reliable work handling, recovery, observability and operator visibility rather than attempting to implement every extended requirement in the handbook.

The following areas were not implemented as full production-grade systems:

- Multi-machine distributed deployment.
- Production authentication and authorization.
- Large-scale distributed coordination.
- Full production deployment orchestration.
- Advanced cache consistency infrastructure.
- Production-scale monitoring and observability.

## 2. Decisions

### Python, FastAPI and SQLite

I chose Python with FastAPI because it allowed me to build the platform and HTTP interface quickly while keeping the implementation understandable.

SQLite was selected because the challenge requires a single-machine, local-only system. It provides persistent state without introducing a separate database service.

### Persistent work state

Accepted work is persisted before it is handed to a worker. This means the platform can recover accepted work after a process restart instead of relying only on in-memory state.

### Bounded retries

Retries use a limit rather than continuing forever. A temporary worker failure can therefore recover automatically, while a permanently broken worker eventually becomes a visible failure instead of creating an infinite restart loop.

### Idempotency

Work has a stable identifier. Repeated submission or delivery of the same identifier can be detected and handled explicitly instead of silently creating independent duplicate work.

### Event history

Important work, worker and operator actions are recorded so that an operator can reconstruct what happened rather than relying only on current state.

### Operator dashboard

I chose a local web dashboard because the challenge asks for an operator view that can be understood without opening log files or attaching a debugger.

## 3. Failure behaviour

### Worker failure during processing

If a worker fails while processing work, the persisted work remains available to the platform. The recovery mechanism can schedule another attempt according to the retry policy.

### Platform restart

Accepted work is stored persistently, so restarting the platform does not intentionally discard accepted work.

### Repeated worker crashes

A worker that repeatedly fails does not receive unlimited restart attempts. Recovery attempts are bounded. Once the configured limit is reached, the failure becomes visible to the operator.

### Duplicate work

The same work identifier can be detected as a duplicate. The platform does not silently treat the duplicate as unrelated new work.

### Failed work

Work that cannot complete within its allowed retry budget reaches a visible failed state instead of disappearing or retrying indefinitely.

### Release rollback

The release workflow stores release state and provides a rollback operation so that the previous known release state can be restored without manually reconstructing it.

### Failure simulation

The project includes mechanisms for deliberately triggering failure scenarios so that the recovery behaviour can be demonstrated during review.

## 4. Limits

This is a focused engineering challenge implementation rather than a production replacement for a distributed platform serving millions of jobs.

The design is intended for the challenge scale of a few thousand work items and a backlog around ten thousand.

The implementation does not provide:

- Multi-machine fault tolerance.
- Production-grade authentication.
- Cloud deployment.
- Full distributed consensus or coordination.
- Production-scale monitoring.
- Complete implementation of every extended NEXUS requirement.

The retry, recovery and storage configuration also have finite limits. These are deliberate design choices so that failures become visible instead of creating unbounded resource usage.

## 5. Confidence

I ran the automated test suite during development.

Current result:

    40 passed, 2 warnings

The tests cover important areas including:

- Work dispatch.
- Persistent work state.
- Idempotency.
- Retry behaviour.
- Worker recovery.
- Worker health.
- Operator behaviour.

I also verified that the local application can be started and that the operator dashboard is accessible through the local server.

The automated tests provide confidence in the implemented paths. I have more confidence in the core work/retry/recovery behaviour than in areas that are intentionally limited or simplified.

The remaining warnings are dependency deprecation warnings and did not cause test failures.

## 6. Next

With another six hours, I would improve the project in this order:

1. Perform a completely clean-machine run using only the README instructions.
2. Add more end-to-end failure demonstrations for the reviewer.
3. Strengthen release rollout and rollback behaviour.
4. Improve backlog recovery with explicit rate limiting.
5. Add stronger consistency checking and cache-age handling.
6. Improve the operator view so that release events, worker failures and work failures are easier to correlate.
7. Add more tests around restart timing and failure boundaries.

The main priority would remain reliability and demonstrable failure recovery rather than adding a large number of unrelated features.