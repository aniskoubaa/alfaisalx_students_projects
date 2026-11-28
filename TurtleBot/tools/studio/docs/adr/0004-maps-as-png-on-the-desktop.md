# ADR-0004: The desktop turns occupancy grids into PNG; the browser gets small events

**Status:** Accepted (2026-11-12; queue replace rule added 2026-11-14)

## Context

A campus map at 5 cm per cell can have millions of cells. The live map arrives about once a second while mapping. The
browser receives everything else through one Server-Sent Events stream (status, lidar, pose, logs), which must stay
responsive, and the bridge's single output queue also carries command replies, including the e-stop reply.

## Decision

The bridge sends a map event only when a new map arrived: the grid sampled to at most `max_cells` cells, one byte per
cell, zlib compressed and base64 encoded. The desktop decodes it once into an 8-bit grey PNG (free 254, occupied 0,
unknown 205), keeps only the newest one (`MapStore`), and publishes a slim event without the data. The page fetches
`/api/map/live.png` when the sequence number changes. In the bridge's output queue at most one map event waits: a
newer one replaces it.

## Consequences

- The event stream never carries large payloads; replies never wait behind old maps.
- One decoder (Python, standard library PNG writer), one memory bound (one PNG).
- The page treats a lower sequence number as a new bridge or a new mapping run and starts a new picture.
- Tests: PNG encoder and decoder round trip, bad and oversized payloads (`test_studio_mapping_desktop.py`), the keyed
  queue (`test_studio_mapping.py`), the store and sequence rules (vitest, `features/mapping`).

## Alternatives considered

- Send the grid to the browser and decode there: larger events on the shared stream, decoding in every open page.
- Serve the robot's PGM files directly: only works for saved maps, not the live one.
