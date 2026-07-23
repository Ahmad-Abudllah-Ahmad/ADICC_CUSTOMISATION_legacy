# Why build on a construction platform

## The position, in one sentence

OpenConstructionERP is one open platform for building any construction
application. Not a horizontal business toolkit that happens to have a
construction template, a platform whose core, data and standards are
construction from the ground up.

That distinction matters when you decide where to build.

## Horizontal platforms make you supply the hard part

A general low-code or ERP platform gives you tables, forms, workflows and an
API. That is genuinely useful, and it is also the easy 20 percent of a
construction product. It leaves you to build the hard 80 percent yourself:

- a cost database with real rates, units and regional factors,
- quantity takeoff from drawings and models,
- classification and measurement standards such as DIN 276, NRM, GAEB and
  MasterFormat,
- a canonical way to carry geometry and quantities from any CAD or BIM source,
- validation that knows what a complete, sane bill of quantities looks like.

Every construction team that builds on a horizontal platform rebuilds those
same foundations, badly and in isolation, because the platform has no opinion
about construction.

## This platform ships the hard part

OpenConstructionERP inverts that. The construction foundations are the core,
and they are already here in the repository:

- Cost databases and rate management (`backend/app/modules/costs`,
  `backend/app/modules/catalog`) with a marketplace catalog of regional cost
  bases in `backend/app/core/marketplace.py`.
- Conceptual and detailed estimating, from an order-of-magnitude model
  (`backend/app/modules/rom_estimate`) through the bill of quantities
  (`backend/app/modules/boq`).
- Takeoff from PDF drawings (`backend/app/modules/takeoff`,
  `backend/app/modules/dwg_takeoff`).
- A validation engine that is a first-class part of the workflow, with built-in
  rule sets for the common measurement and classification standards
  (`backend/app/core/validation`).
- Tendering, procurement, scheduling, BIM coordination, field capture and more
  than 150 first-party modules under `backend/app/modules/`.

You build your application as another module that stands on those, instead of
rebuilding them. Your five-person team ships a focused product because the
platform already carries the construction weight.

## Construction is the moat, on purpose

The reason to keep the platform construction-specific is the same reason it is
valuable to build on. The moat is the domain: real cost data, takeoff, BIM and
canonical geometry, and the standards that govern measurement and classification.
Those are expensive to build, slow to get right, and exactly what a construction
product needs on day one. A horizontal platform cannot have them without
becoming a construction platform. So we stay one, and we make it open.

If your idea is a construction app, an estimating tool, a site-management tool,
a compliance checker, a regional cost connector, a takeoff assistant, then you
are building in the right place. If your idea is not construction, this is not
your platform, and that is a deliberate choice rather than a gap.

## The licence model

OpenConstructionERP is released under AGPL-3.0 for the community edition, with a
separate commercial licence for organisations that need terms the AGPL does not
give them. In practice:

- The community edition is the full modular platform. You can run it, study it,
  modify it and build modules on it under the AGPL.
- Because the licence is AGPL, a modified version offered to others over a
  network carries the AGPL obligation to share the corresponding source. If you
  distribute or host a modified platform, plan for that.
- The commercial licence exists for enterprise and white-label situations where
  the AGPL terms do not fit. That is a separate agreement, not a paywalled core.

Nothing in the module system is gated behind the commercial licence. The loader,
the event bus, the hook registry, the validation engine, the scaffolder and the
module template are all part of the open core. The developer story in this
section works entirely on the community edition.

## What "open" buys you as a builder

- No vendor lock-in. Every data model is yours to read, and the export paths are
  open formats. A module you write is plain Python against documented core APIs.
- No black-box behaviour. When you need to know exactly what the loader,
  validation or event bus does, you read the source. This section points you at
  the exact files.
- Upgradeable. Because the extension points are events, hooks and modules, you
  extend the platform without editing core files, and you take the next release
  without re-applying a patch. See [Extend, do not fork](./extend-dont-fork.md).

## Next

Read [How the platform works for builders](./how-it-works-for-builders.md) for
the mechanics, then build your first module with the
[10-minute tutorial](./first-module-in-10-minutes.md).
