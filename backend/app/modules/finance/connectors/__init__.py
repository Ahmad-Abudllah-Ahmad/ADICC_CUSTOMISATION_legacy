# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Finance ERP / accounting connectors.

A connector moves money documents between OpenConstructionERP and an
external accounting or ERP system. The first concrete connector is
file-based (CSV / JSON drop), but the contract in :mod:`base` is
transport-agnostic so a later SFTP / REST / SAP connector slots into the
same registry, service and UI without touching the rest of the finance
module.

Public surface:

* :class:`~app.modules.finance.connectors.base.Connector` - abstract base.
* :data:`~app.modules.finance.connectors.registry.connector_registry` -
  the process-wide registry endpoints and the service talk to.
* :func:`~app.modules.finance.connectors.registry.register_builtin_connectors`
  - called from the finance module ``on_startup`` hook.
"""

from app.modules.finance.connectors.base import (
    Connector,
    ConnectorConfigError,
    ConnectorError,
    ConnectorField,
    PushPayload,
    SyncResult,
    to_decimal,
)
from app.modules.finance.connectors.registry import (
    ConnectorRegistry,
    connector_registry,
    register_builtin_connectors,
)

__all__ = [
    "Connector",
    "ConnectorConfigError",
    "ConnectorError",
    "ConnectorField",
    "ConnectorRegistry",
    "PushPayload",
    "SyncResult",
    "connector_registry",
    "register_builtin_connectors",
    "to_decimal",
]
