# Build on OpenConstructionERP

OpenConstructionERP is an open platform for building construction software. The
same modular core that runs the shipped product, projects, bills of quantities,
takeoff, cost databases, validation, tendering and more than 150 other modules,
is the core you build on. Adding a capability means writing a module, not
editing the platform.

This section is the developer story. It explains why the platform is scoped to
construction, how the plugin model actually works, and how to ship your first
module.

## Read in this order

1. [Why build on a construction platform](./why-build-on-construction.md)
   The positioning and the licence model in plain terms. One platform to build
   any construction app, and why construction stays the moat.

2. [How the platform works for builders](./how-it-works-for-builders.md)
   The module loader, the manifest, auto-discovery and auto-mounting, the
   module file conventions, the event bus, the hook registry, the building
   blocks that make up the module SDK, and how modules reach the marketplace.
   Every claim is tied to a file in the repository.

3. [Your first module in 10 minutes](./first-module-in-10-minutes.md)
   A copy-pasteable walkthrough. Scaffold a real module from the template,
   register a model, a schema, a router and one validation rule, wire the
   migration, and watch the loader mount it on the next restart.

4. [Extend, do not fork](./extend-dont-fork.md)
   Change core behaviour with events and hooks instead of editing core files,
   so you can upgrade the platform without re-applying a patch every release.

## Companion guides

The [module development quickstart](../module-development/quickstart.md) and the
[BOQ importer plugin walkthrough](../module-development/boq-importer-plugin.md)
cover the same ground from a task angle. The platform docs here are the
reference story; those are worked examples.

## The short version

A module is a Python package under `backend/app/modules/<name>/` with a
`manifest.py`. On boot the loader in `backend/app/core/module_loader.py`
discovers every manifest, sorts modules by their declared dependencies, imports
each package, registers its database models, mounts its router under
`/api/v1/<name>/`, wires its hooks, events and validation rules, and calls its
`on_startup()` hook. There is no central registry file to edit and no router
include to add. Drop the package in, restart, and it is live.
