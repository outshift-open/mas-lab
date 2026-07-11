<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# ADR 0002 — Observability event model: an announced stream, not a query interface

**Status:** Accepted
**Date:** 2026-07-10

## Context

Every call the runtime makes on an agent's behalf — a tool invocation, a model
call, a memory read or write — passes through the same shape of crossing: a
governance check before the call, the call itself, and a governance check
after. Each of these is a moment worth recording, and not only the fact that
it happened. What made governance decide what it decided, what a human
answered when asked, what the runtime did when a call failed and had to be
retried or abandoned — all of that is information some downstream consumer
will eventually need.

There are two general shapes for making that information available. One is a
store that answers questions when asked: something else, later, requests
"what did governance decide for this call" and receives an answer. The other
is a stream that announces what happened as it happens: each crossing writes
a self-describing record the moment it occurs, and whatever wants to know
subscribes to or later reads that stream rather than asking a question of a
live system.

## Decision

The runtime records every boundary crossing as a self-contained record,
written once, at the moment the crossing happens, and never asked for again.
Every record carries a single linking value — a correlation id — shared by
every other record produced by the same call. A reader who wants the whole
story of one call (its governance check going in, the call itself, its
governance check coming out) reassembles that story by collecting every
record with the same correlation id, in the order they were written.
Nothing needs to be asked for in advance, and nothing needs a live system to
answer it.

## Why an announced stream, and not a query interface

**A run outlives the process that produced it.** A benchmark result gets
inspected during a code review weeks later; an incident gets reconstructed
months after the fact; a lab result gets compared against a previous one that
no longer has a running process behind it. A written record survives all of
these unchanged. A live store that answers questions only survives them if it
is itself turned into a written record at some point — at which point it was
a stream all along, just a later one.

**More than one thing wants to know what happened, and they don't
coordinate with each other.** A single call's outcome may be read by a file
written for later inspection, by an external monitoring system, by a plot
built from the run's history — none of which run at the same time as the
call itself, none of which know about each other, and none of which should
have to. An announced stream lets each of these subscribe or read
independently, at its own pace, without agreeing on a shared protocol for
asking questions of a live run. A query interface would require all of them
to exist and coordinate while the call is still in progress.

**Self-contained does not mean disconnected.** Each record is deliberately
kept small — it describes one crossing, not the whole call — but it is never
isolated, because the correlation id ties it back to everything else the same
call produced. This is already the shape used elsewhere in the runtime: the
context handed to a model call is recorded as its own small record, linked to
the call it feeds, rather than folded into one large combined record. The
same principle now applies to governance: a decision at the boundary is
recorded as its own record — what was decided, and why — linked by
correlation id to the call it gates, rather than bundled into the call
record itself or withheld until asked for.

## What each record carries, and what is left to be asked for

A record carries the minimum that lets it stand on its own: what kind of
crossing this was, when it happened, which call it belongs to. Beyond that
minimum, the runtime does not try to anticipate every question a future
governance rule, a future audit, or a future visualization might have.
Records that describe a governance outcome carry the decision and a short,
human-readable reason for it — not because every consumer needs the reason,
but because withholding it would mean the explanation is lost forever the
moment the call moves on, and there is no way to go back and ask for it
later. Anything that can instead be computed by a reader from the stream
itself — a chain of retries, a call that a human approved — is left to be
computed by the reader, rather than pre-packaged into the record.

This is the same reasoning applied consistently at both ends: record
everything that would otherwise be lost the instant the moment passes, and
leave everything else to whoever reads the stream afterward. A prior version
of the runtime's boundary recording dropped several kinds of crossings
outright — a human's actual answer to an approval request, a call that
failed past its retry budget, the semantic outcome of a governance check as
distinct from its timing — because nothing downstream had been built yet to
read them. Those crossings still happened; they were simply never written
down, and so were unrecoverable afterward. Every kind of crossing the runtime
performs is now written to the stream, whether or not every current consumer
uses every kind yet.

## Forward compatibility with graph-shaped consumption

A stream of small, correlation-linked records is already shaped like a graph
without committing to being one: each record is a node's worth of
information, and correlation ids (together with the parent/child structure
already carried by nested calls) are its edges. A future consumer that wants
to read the same run's history as a graph — for exploration, for a richer
visualization, for cross-run comparison — does not require the runtime to
record anything differently. It requires only a different way of reading
what is already written: a translation step that turns the flat stream into
nodes and relationships, sitting in front of whatever already consumes the
stream today. The recording side of this design does not need to change
for that translation step to exist later.

## Related

- [Contracts](contracts.md) — where this stream fits among the runtime's
  other boundaries
- [ADR 0001](adr-0001-lab-terminology.md) — repository terminology (unrelated
  decision, same record format)
