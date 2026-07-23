# OpenConstructionERP v6.4.2

This is a maintenance release on top of v6.4.1. It fixes two geometry bugs that placed BIM and 3D models far from the ground, makes Partner Packs much easier to create and install without a source checkout, and tidies up the continuous integration run. Nothing here changes day-to-day workflows, and upgrading is safe.

## Models sit at ground level

Two unrelated bugs had been throwing model geometry off into the distance, and both are fixed.

A model authored in millimetres or in imperial units used to load with its elements scattered up to a thousand times too far from the origin. The element extents were already being converted from the file's declared length unit to metres, but the placement coordinates that say where each element sits were read in the raw file units, so the two did not agree and the viewer could not frame the building. Placements are now scaled the same way the quantities are. Files already in SI metres or with no unit declared behave exactly as before, and files in feet are handled too.

Separately, the 3D tiles that a project map serves were georeferenced several kilometres up in the air. The height was computed by a copy of a coordinate conversion that subtracted the wrong Earth radius, which pushed every model a latitude-dependent five to thirteen kilometres above the ellipsoid. That inline math is replaced by the shared, tested conversion helper, so a one-metre cube in Denver now spans zero to one metre above the ground instead of nearly nine kilometres, and any anchor altitude you set is still honoured.

These close issue #53 and issue #48, and both fixes are pinned by regression tests for millimetre, imperial and metre models.

## Partner Packs are easier to create and install

A Partner Pack is a bundle of declarative presets. It ships no code and no data, and the app never executes it, so installing one is low risk. This release rounds out the create, install and apply flow so it works for everyone, including pip and server installs that have no repository on disk.

You can now scaffold a valid, ready-to-discover pack from the command line with `pack new`. You can drop a pack folder or a .zip into the runtime data directory's packs folder and pick it up with the Rescan button. Or, as an admin, you can upload the pack .zip directly in the app from Modules then Partner Packs. None of these routes need a backend restart, and the pip-package route is still available for anyone who prefers it. A dropped or uploaded pack is listed but never activated on its own; you still apply it deliberately, and applying stays reversible.

The in-app developer guide on the Partner Packs page was rewritten to match how this actually works, and the old, misleading instruction to restart the backend has been removed.

Pack archives are handled carefully. Every dropped or uploaded zip is extracted through a single hardened routine that rejects path traversal, symlinks, absolute paths, drive letters and backslash members, validates each entry, and stages to a temporary directory before an atomic move into place. The admin upload endpoint is size-capped and confirms the file is genuinely a zip before reading it.

## Smaller fixes and housekeeping

The X-DDC-License response header is ASCII-only again. It previously carried a non-ASCII separator character that some HTTP clients and test tools rejected, and it now uses a plain hyphen. The header is a decorative authorship marker and nothing depends on its exact text.

This release also includes conservative dependency fixes for flagged advisories, none of which affect the running application. python-multipart is raised to 0.0.27 for a multipart-parsing denial-of-service that is reachable through file uploads, and pyarrow to 23.0.1 for a patch in the same series. On the frontend, the uuid library bundled inside exceljs is pinned to 11.1.1 to clear a transitive advisory. The remaining flagged items are all inside the vitest test tooling, which is a development dependency that never ships in the build or runs in production, so that one is being handled separately as a tested change because it is a major version.

The production Docker deployment is now documented, covering both the single-image build and the split backend and nginx setup, including the upload size limit for drawings and CAD files, the module-worker content type the takeoff viewer needs, and the WebSocket upgrade for live notifications and presence.

Finally, build and test hygiene. The backend test collection no longer aborts when an optional dependency is not installed, so the continuous integration run completes cleanly, and a batch of frontend unit tests that had drifted from the components they cover was brought back in line. None of this changes how the app behaves.

## Upgrade notes

There are no database migrations and no breaking changes in this release. Upgrade in place the usual way for your install: `pip install --upgrade openconstructionerp`, or pull the new image if you run with Docker.
