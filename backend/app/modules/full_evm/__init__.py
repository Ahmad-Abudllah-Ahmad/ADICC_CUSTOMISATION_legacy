# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Full EVM module.

Earned Value Management forecasts, S-curve computation, and integration
with finance EVM snapshots.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions and the forecast batch job."""
    from app.modules.full_evm.job import register_forecast_job_handler
    from app.modules.full_evm.permissions import register_full_evm_permissions

    register_full_evm_permissions()
    register_forecast_job_handler()
