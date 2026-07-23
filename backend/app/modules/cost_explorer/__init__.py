# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Cost Explorer module.

A search-first workspace over the cost and resource catalogs. It answers the
question an estimator actually starts from - "I know the materials, labour and
plant, which priced work uses them?" - and three neighbours of it:

* **By resources** - given a set of resources, the priced work items that
  consume them, ranked (the reverse of the usual work -> resources lookup).
* **Find work** - semantic and keyword search across the installed price bases.
* **Compare across bases** - the same scope priced in every loaded region.
* **Substitute** - swap a resource on a work item and see the rate move.

The only new persistent object is the resource -> work reverse index
(:class:`app.modules.cost_explorer.models.CostItemResource`); everything else
reuses the existing cost and resource models, the semantic index and the match
services.

The package does no import-time database work: the pure engines
(:mod:`app.modules.cost_explorer.ranking`, :mod:`app.modules.cost_explorer.pricing`)
are importable on any interpreter, so they can be unit tested without a database
or the app graph. Permission registration and the one-time reverse-index build
are deferred to :func:`on_startup`, called by the module loader.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions and seed the reverse index."""
    from app.modules.cost_explorer.permissions import register_cost_explorer_permissions
    from app.modules.cost_explorer.service import build_index_if_empty

    register_cost_explorer_permissions()
    await build_index_if_empty()
