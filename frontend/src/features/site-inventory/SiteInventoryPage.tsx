// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import clsx from 'clsx';
import {
  AlertTriangle,
  ArrowDownToLine,
  ArrowLeftRight,
  Boxes,
  Package,
  PackageMinus,
  Plus,
  Trash2,
  Warehouse,
  X,
} from 'lucide-react';
import { Badge, Button, Card, EmptyState, SkeletonTable, TabBar } from '@/shared/ui';
import { PageHeader } from '@/shared/ui/PageHeader';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { RequiresProject } from '@/shared/auth/RequiresProject';
import { getErrorMessage } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import {
  createItem,
  createLocation,
  fetchItems,
  fetchLocations,
  fetchMovements,
  fetchStockOnHand,
  recordMovement,
  MOVEMENT_TYPES,
  type LocationCreate,
  type MovementCreate,
  type MovementType,
  type StockItem,
  type StockItemCreate,
  type StockLocation,
  type StockMovement,
  type StockOnHandRow,
} from './api';

/* -- Shared styling + small helpers --------------------------------------- */

const inputCls =
  'h-10 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm text-content-primary focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';
const textareaCls =
  'w-full rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm text-content-primary focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue resize-none';

type TabId = 'stock' | 'movements' | 'items' | 'locations';
type BadgeVariant = 'neutral' | 'blue' | 'success' | 'warning' | 'error';
type BalanceStatus = 'ok' | 'low' | 'negative';

const MOVEMENT_TYPE_CONFIG: Record<MovementType, { icon: React.ElementType; variant: BadgeVariant }> = {
  INBOUND: { icon: ArrowDownToLine, variant: 'success' },
  CONSUMPTION: { icon: PackageMinus, variant: 'blue' },
  WASTE: { icon: Trash2, variant: 'error' },
  TRANSFER: { icon: ArrowLeftRight, variant: 'neutral' },
};

/** English fallback labels for the movement-type enum (real text goes through
 *  the site_inventory.movement_type_* i18n keys). */
const MOVEMENT_TYPE_LABEL: Record<MovementType, string> = {
  INBOUND: 'Inbound',
  CONSUMPTION: 'Consumption',
  WASTE: 'Waste',
  TRANSFER: 'Transfer',
};

/** Parse a decimal string to a number, or NaN when absent / unparseable. */
function toNumber(value: string | null | undefined): number {
  if (value == null || value.trim() === '') return Number.NaN;
  return Number.parseFloat(value);
}

/* -- Reusable modal shell -------------------------------------------------- */

function Modal({
  title,
  onClose,
  children,
  footer,
  maxWidth = 'max-w-lg',
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer: React.ReactNode;
  maxWidth?: string;
}) {
  const { t } = useTranslation();
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-lg p-4 animate-fade-in">
      <div
        className={clsx(
          'w-full bg-surface-elevated rounded-xl shadow-xl border border-border animate-card-in max-h-[90vh] overflow-y-auto',
          maxWidth,
        )}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-light">
          <h2 className="text-lg font-semibold text-content-primary">{title}</h2>
          <button
            onClick={onClose}
            aria-label={t('site_inventory.close', { defaultValue: 'Close' })}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-content-tertiary hover:bg-surface-secondary hover:text-content-primary transition-colors"
          >
            <X size={18} />
          </button>
        </div>
        <div className="px-6 py-4 space-y-4">{children}</div>
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border-light">
          {footer}
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-content-primary mb-1.5">
        {label}
        {required && <span className="text-semantic-error"> *</span>}
      </label>
      {children}
      {hint && <p className="mt-1 text-xs text-content-tertiary">{hint}</p>}
    </div>
  );
}

function InlineError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <Card padding="lg" className="flex flex-col items-center gap-3 text-center">
      <AlertTriangle size={24} className="text-semantic-error" />
      <p className="text-sm text-content-secondary">{getErrorMessage(error)}</p>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        {t('site_inventory.retry', { defaultValue: 'Retry' })}
      </Button>
    </Card>
  );
}

/* -- Create-location modal ------------------------------------------------- */

function CreateLocationModal({
  onClose,
  onSubmit,
  isPending,
}: {
  onClose: () => void;
  onSubmit: (data: LocationCreate) => void;
  isPending: boolean;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [address, setAddress] = useState('');
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [touched, setTouched] = useState(false);

  const nameError = touched && name.trim().length === 0;
  const submit = () => {
    setTouched(true);
    if (name.trim().length === 0) return;
    onSubmit({
      name: name.trim(),
      code: code.trim() || undefined,
      address: address.trim() || undefined,
      latitude: latitude.trim() || undefined,
      longitude: longitude.trim() || undefined,
    });
  };

  return (
    <Modal
      title={t('site_inventory.new_location_title', { defaultValue: 'New storage location' })}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={isPending}>
            {t('site_inventory.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant="primary"
            onClick={submit}
            loading={isPending}
            icon={!isPending ? <Plus size={16} /> : undefined}
          >
            {t('site_inventory.create_location', { defaultValue: 'Create location' })}
          </Button>
        </>
      }
    >
      <Field label={t('site_inventory.field_name', { defaultValue: 'Name' })} required>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
          placeholder={t('site_inventory.name_placeholder', {
            defaultValue: 'e.g. Main yard, Container B, Level 2 store',
          })}
          className={clsx(inputCls, nameError && 'border-semantic-error focus:ring-red-300')}
        />
        {nameError && (
          <p className="mt-1 text-xs text-semantic-error">
            {t('site_inventory.name_required', { defaultValue: 'Name is required' })}
          </p>
        )}
      </Field>
      <Field label={t('site_inventory.field_code', { defaultValue: 'Code' })}>
        <input value={code} onChange={(e) => setCode(e.target.value)} className={inputCls} />
      </Field>
      <Field label={t('site_inventory.field_address', { defaultValue: 'Address' })}>
        <input value={address} onChange={(e) => setAddress(e.target.value)} className={inputCls} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label={t('site_inventory.field_latitude', { defaultValue: 'Latitude' })}>
          <input
            value={latitude}
            onChange={(e) => setLatitude(e.target.value)}
            inputMode="decimal"
            className={inputCls}
          />
        </Field>
        <Field label={t('site_inventory.field_longitude', { defaultValue: 'Longitude' })}>
          <input
            value={longitude}
            onChange={(e) => setLongitude(e.target.value)}
            inputMode="decimal"
            className={inputCls}
          />
        </Field>
      </div>
    </Modal>
  );
}

/* -- Create-item modal ----------------------------------------------------- */

function CreateItemModal({
  locations,
  onClose,
  onSubmit,
  isPending,
}: {
  locations: StockLocation[];
  onClose: () => void;
  onSubmit: (data: StockItemCreate) => void;
  isPending: boolean;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [sku, setSku] = useState('');
  const [unit, setUnit] = useState('');
  const [unitCost, setUnitCost] = useState('');
  const [currency, setCurrency] = useState('');
  const [reorderPoint, setReorderPoint] = useState('');
  const [defaultLocationId, setDefaultLocationId] = useState('');
  const [touched, setTouched] = useState(false);

  const nameError = touched && name.trim().length === 0;
  const submit = () => {
    setTouched(true);
    if (name.trim().length === 0) return;
    onSubmit({
      name: name.trim(),
      sku: sku.trim() || undefined,
      unit: unit.trim() || undefined,
      standard_unit_cost: unitCost.trim() || undefined,
      currency: currency.trim() || undefined,
      reorder_point: reorderPoint.trim() || undefined,
      default_location_id: defaultLocationId || undefined,
    });
  };

  return (
    <Modal
      title={t('site_inventory.new_item_title', { defaultValue: 'New stock item' })}
      onClose={onClose}
      maxWidth="max-w-xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={isPending}>
            {t('site_inventory.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant="primary"
            onClick={submit}
            loading={isPending}
            icon={!isPending ? <Plus size={16} /> : undefined}
          >
            {t('site_inventory.create_item', { defaultValue: 'Create item' })}
          </Button>
        </>
      }
    >
      <Field label={t('site_inventory.field_name', { defaultValue: 'Name' })} required>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
          placeholder={t('site_inventory.item_name_placeholder', {
            defaultValue: 'e.g. Ready-mix concrete C30/37',
          })}
          className={clsx(inputCls, nameError && 'border-semantic-error focus:ring-red-300')}
        />
        {nameError && (
          <p className="mt-1 text-xs text-semantic-error">
            {t('site_inventory.name_required', { defaultValue: 'Name is required' })}
          </p>
        )}
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label={t('site_inventory.field_sku', { defaultValue: 'SKU' })}>
          <input value={sku} onChange={(e) => setSku(e.target.value)} className={inputCls} />
        </Field>
        <Field label={t('site_inventory.field_unit', { defaultValue: 'Unit of measure' })}>
          <input
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            placeholder={t('site_inventory.unit_placeholder', { defaultValue: 'e.g. m3, kg, pcs' })}
            className={inputCls}
          />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label={t('site_inventory.field_unit_cost', { defaultValue: 'Standard unit cost' })}>
          <input
            value={unitCost}
            onChange={(e) => setUnitCost(e.target.value)}
            inputMode="decimal"
            className={inputCls}
          />
        </Field>
        <Field label={t('site_inventory.field_currency', { defaultValue: 'Currency' })}>
          <input
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            placeholder="EUR"
            className={inputCls}
          />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field
          label={t('site_inventory.field_reorder', { defaultValue: 'Reorder point' })}
          hint={t('site_inventory.reorder_hint', {
            defaultValue: 'Balances at or below this level are flagged as low stock.',
          })}
        >
          <input
            value={reorderPoint}
            onChange={(e) => setReorderPoint(e.target.value)}
            inputMode="decimal"
            className={inputCls}
          />
        </Field>
        <Field label={t('site_inventory.field_default_location', { defaultValue: 'Default location' })}>
          <select
            value={defaultLocationId}
            onChange={(e) => setDefaultLocationId(e.target.value)}
            className={inputCls}
          >
            <option value="">
              {t('site_inventory.no_location_option', { defaultValue: 'No default location' })}
            </option>
            {locations.map((loc) => (
              <option key={loc.id} value={loc.id}>
                {loc.name}
              </option>
            ))}
          </select>
        </Field>
      </div>
    </Modal>
  );
}

/* -- Record-movement modal ------------------------------------------------- */

function RecordMovementModal({
  items,
  locations,
  onClose,
  onSubmit,
  isPending,
}: {
  items: StockItem[];
  locations: StockLocation[];
  onClose: () => void;
  onSubmit: (data: MovementCreate) => void;
  isPending: boolean;
}) {
  const { t } = useTranslation();
  const [itemId, setItemId] = useState('');
  const [movementType, setMovementType] = useState<MovementType>('INBOUND');
  const [quantity, setQuantity] = useState('');
  const [unitCost, setUnitCost] = useState('');
  const [currency, setCurrency] = useState('');
  const [locationId, setLocationId] = useState('');
  const [toLocationId, setToLocationId] = useState('');
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState('');
  const [touched, setTouched] = useState(false);

  const isTransfer = movementType === 'TRANSFER';
  const qtyNum = toNumber(quantity);
  const itemError = touched && itemId === '';
  const qtyError = touched && !(qtyNum > 0);
  const transferError =
    touched && isTransfer && (locationId === '' || toLocationId === '' || locationId === toLocationId);
  const canSubmit =
    itemId !== '' &&
    qtyNum > 0 &&
    (!isTransfer || (locationId !== '' && toLocationId !== '' && locationId !== toLocationId));

  const onItemChange = (nextId: string) => {
    setItemId(nextId);
    const chosen = items.find((it) => it.id === nextId);
    if (chosen) {
      if (currency.trim() === '' && chosen.currency) setCurrency(chosen.currency);
      if (unitCost.trim() === '' && chosen.standard_unit_cost) setUnitCost(chosen.standard_unit_cost);
    }
  };

  const submit = () => {
    setTouched(true);
    if (!canSubmit) return;
    onSubmit({
      item_id: itemId,
      movement_type: movementType,
      quantity: quantity.trim(),
      unit_cost: unitCost.trim() || undefined,
      currency: currency.trim() || undefined,
      location_id: locationId || undefined,
      to_location_id: isTransfer ? toLocationId || undefined : undefined,
      occurred_at: date ? new Date(date).toISOString() : undefined,
      note: note.trim() || undefined,
    });
  };

  return (
    <Modal
      title={t('site_inventory.record_movement_title', { defaultValue: 'Record stock movement' })}
      onClose={onClose}
      maxWidth="max-w-xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={isPending}>
            {t('site_inventory.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button variant="primary" onClick={submit} loading={isPending} disabled={!canSubmit}>
            {t('site_inventory.record', { defaultValue: 'Record' })}
          </Button>
        </>
      }
    >
      {/* Movement type selector */}
      <Field label={t('site_inventory.field_movement_type', { defaultValue: 'Movement type' })}>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {MOVEMENT_TYPES.map((mt) => {
            const cfg = MOVEMENT_TYPE_CONFIG[mt];
            const Icon = cfg.icon;
            const selected = movementType === mt;
            return (
              <button
                key={mt}
                type="button"
                onClick={() => setMovementType(mt)}
                className={clsx(
                  'flex items-center gap-2 rounded-lg border-2 px-3 py-2.5 text-left transition-all',
                  selected
                    ? 'border-oe-blue bg-oe-blue-subtle text-content-primary'
                    : 'border-border bg-surface-primary text-content-tertiary hover:border-border-light hover:bg-surface-secondary',
                )}
              >
                <Icon size={16} className="shrink-0" />
                <span className="text-xs font-semibold">
                  {t(`site_inventory.movement_type_${mt.toLowerCase()}`, {
                    defaultValue: MOVEMENT_TYPE_LABEL[mt],
                  })}
                </span>
              </button>
            );
          })}
        </div>
      </Field>

      <Field label={t('site_inventory.field_item', { defaultValue: 'Item' })} required>
        <select
          value={itemId}
          onChange={(e) => onItemChange(e.target.value)}
          className={clsx(inputCls, itemError && 'border-semantic-error focus:ring-red-300')}
        >
          <option value="">{t('site_inventory.select_item', { defaultValue: 'Select an item' })}</option>
          {items.map((it) => (
            <option key={it.id} value={it.id}>
              {it.name}
              {it.unit ? ` (${it.unit})` : ''}
            </option>
          ))}
        </select>
        {itemError && (
          <p className="mt-1 text-xs text-semantic-error">
            {t('site_inventory.item_required', { defaultValue: 'Select an item' })}
          </p>
        )}
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label={t('site_inventory.field_quantity', { defaultValue: 'Quantity' })} required>
          <input
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            inputMode="decimal"
            placeholder={t('site_inventory.quantity_placeholder', { defaultValue: 'e.g. 12.5' })}
            className={clsx(inputCls, qtyError && 'border-semantic-error focus:ring-red-300')}
          />
          {qtyError && (
            <p className="mt-1 text-xs text-semantic-error">
              {t('site_inventory.quantity_required', {
                defaultValue: 'Enter a quantity greater than zero',
              })}
            </p>
          )}
        </Field>
        <Field label={t('site_inventory.field_date', { defaultValue: 'Date' })}>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className={inputCls}
          />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label={t('site_inventory.field_unit_cost_optional', { defaultValue: 'Unit cost' })}>
          <input
            value={unitCost}
            onChange={(e) => setUnitCost(e.target.value)}
            inputMode="decimal"
            className={inputCls}
          />
        </Field>
        <Field label={t('site_inventory.field_currency', { defaultValue: 'Currency' })}>
          <input value={currency} onChange={(e) => setCurrency(e.target.value)} className={inputCls} />
        </Field>
      </div>

      <Field
        label={
          isTransfer
            ? t('site_inventory.field_from_location', { defaultValue: 'From location' })
            : t('site_inventory.field_location', { defaultValue: 'Location' })
        }
        required={isTransfer}
      >
        <select
          value={locationId}
          onChange={(e) => setLocationId(e.target.value)}
          className={clsx(inputCls, transferError && 'border-semantic-error focus:ring-red-300')}
        >
          <option value="">{t('site_inventory.none_option', { defaultValue: 'None' })}</option>
          {locations.map((loc) => (
            <option key={loc.id} value={loc.id}>
              {loc.name}
            </option>
          ))}
        </select>
      </Field>

      {isTransfer && (
        <Field label={t('site_inventory.field_to_location', { defaultValue: 'To location' })} required>
          <select
            value={toLocationId}
            onChange={(e) => setToLocationId(e.target.value)}
            className={clsx(inputCls, transferError && 'border-semantic-error focus:ring-red-300')}
          >
            <option value="">{t('site_inventory.none_option', { defaultValue: 'None' })}</option>
            {locations.map((loc) => (
              <option key={loc.id} value={loc.id}>
                {loc.name}
              </option>
            ))}
          </select>
          {transferError && (
            <p className="mt-1 text-xs text-semantic-error">
              {t('site_inventory.transfer_needs_locations', {
                defaultValue: 'A transfer needs a source and a different destination location',
              })}
            </p>
          )}
        </Field>
      )}

      <Field label={t('site_inventory.field_note', { defaultValue: 'Note' })}>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          placeholder={t('site_inventory.note_placeholder', {
            defaultValue: 'Optional reference, delivery note or reason',
          })}
          className={textareaCls}
        />
      </Field>
    </Modal>
  );
}

/* -- Main page ------------------------------------------------------------- */

export function SiteInventoryPage() {
  const { t } = useTranslation();
  const { projectId: routeProjectId } = useParams<{ projectId: string }>();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const projectId = routeProjectId || activeProjectId || '';
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const [activeTab, setActiveTab] = useState<TabId>('stock');
  const [showMovementModal, setShowMovementModal] = useState(false);
  const [showItemModal, setShowItemModal] = useState(false);
  const [showLocationModal, setShowLocationModal] = useState(false);

  /* -- Queries ------------------------------------------------------------ */
  const stockQuery = useQuery({
    queryKey: ['site-inventory', 'stock-on-hand', projectId],
    queryFn: () => fetchStockOnHand(projectId),
    enabled: !!projectId,
  });
  const movementsQuery = useQuery({
    queryKey: ['site-inventory', 'movements', projectId],
    queryFn: () => fetchMovements(projectId),
    enabled: !!projectId,
  });
  const itemsQuery = useQuery({
    queryKey: ['site-inventory', 'items', projectId],
    queryFn: () => fetchItems(projectId),
    enabled: !!projectId,
  });
  const locationsQuery = useQuery({
    queryKey: ['site-inventory', 'locations', projectId],
    queryFn: () => fetchLocations(projectId),
    enabled: !!projectId,
  });

  const items = useMemo(() => itemsQuery.data ?? [], [itemsQuery.data]);
  const locations = useMemo(() => locationsQuery.data ?? [], [locationsQuery.data]);
  const movements = useMemo(() => movementsQuery.data ?? [], [movementsQuery.data]);
  const stockRows = useMemo(() => stockQuery.data?.rows ?? [], [stockQuery.data]);

  const itemsById = useMemo(
    () => new Map(items.map((it) => [it.id, it] as const)),
    [items],
  );
  const locationsById = useMemo(
    () => new Map(locations.map((l) => [l.id, l] as const)),
    [locations],
  );
  const reorderById = useMemo(
    () => new Map(items.map((it) => [it.id, it.reorder_point] as const)),
    [items],
  );

  const balanceStatus = useCallback(
    (row: StockOnHandRow): BalanceStatus => {
      const qty = toNumber(row.on_hand);
      if (Number.isFinite(qty) && qty < 0) return 'negative';
      const rp = toNumber(reorderById.get(row.item_id));
      if (Number.isFinite(rp) && Number.isFinite(qty) && qty <= rp) return 'low';
      return 'ok';
    },
    [reorderById],
  );

  const stockSummary = useMemo(() => {
    let low = 0;
    let negative = 0;
    for (const row of stockRows) {
      const status = balanceStatus(row);
      if (status === 'negative') negative += 1;
      else if (status === 'low') low += 1;
    }
    return { tracked: stockRows.length, low, negative };
  }, [stockRows, balanceStatus]);

  const itemName = useCallback(
    (id: string): string =>
      itemsById.get(id)?.name ?? t('site_inventory.unknown_item', { defaultValue: 'Unknown item' }),
    [itemsById, t],
  );
  const locName = useCallback(
    (id: string | null): string => {
      if (!id) return '';
      const loc = locationsById.get(id);
      return loc?.name ?? loc?.code ?? id.slice(0, 8);
    },
    [locationsById],
  );

  /* -- Mutations ---------------------------------------------------------- */
  const toastError = useCallback(
    (e: unknown) =>
      addToast({
        type: 'error',
        title: t('site_inventory.error', { defaultValue: 'Error' }),
        message: getErrorMessage(e),
      }),
    [addToast, t],
  );

  const locationMut = useMutation({
    mutationFn: (data: LocationCreate) => createLocation(projectId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['site-inventory', 'locations', projectId] });
      setShowLocationModal(false);
      addToast({
        type: 'success',
        title: t('site_inventory.location_created', { defaultValue: 'Location created' }),
      });
    },
    onError: toastError,
  });

  const itemMut = useMutation({
    mutationFn: (data: StockItemCreate) => createItem(projectId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['site-inventory', 'items', projectId] });
      setShowItemModal(false);
      addToast({
        type: 'success',
        title: t('site_inventory.item_created', { defaultValue: 'Item created' }),
      });
    },
    onError: toastError,
  });

  const movementMut = useMutation({
    mutationFn: (data: MovementCreate) => recordMovement(projectId, data),
    onSuccess: () => {
      // Recording a movement changes the balance, so refresh the ledger AND the
      // derived stock-on-hand view together so the "on hand" numbers stay live.
      qc.invalidateQueries({ queryKey: ['site-inventory', 'movements', projectId] });
      qc.invalidateQueries({ queryKey: ['site-inventory', 'stock-on-hand', projectId] });
      setShowMovementModal(false);
      addToast({
        type: 'success',
        title: t('site_inventory.movement_recorded', { defaultValue: 'Movement recorded' }),
      });
    },
    onError: toastError,
  });

  /* -- Tabs --------------------------------------------------------------- */
  const countBadge = (n: number) =>
    n > 0 ? (
      <span className="rounded-full bg-surface-secondary px-1.5 text-2xs text-content-tertiary">
        {n}
      </span>
    ) : undefined;

  const tabs = [
    {
      id: 'stock' as const,
      label: t('site_inventory.tab_stock', { defaultValue: 'Stock on hand' }),
      icon: <Boxes size={15} />,
    },
    {
      id: 'movements' as const,
      label: t('site_inventory.tab_movements', { defaultValue: 'Movements' }),
      icon: <ArrowLeftRight size={15} />,
      badge: countBadge(movements.length),
    },
    {
      id: 'items' as const,
      label: t('site_inventory.tab_items', { defaultValue: 'Items' }),
      icon: <Package size={15} />,
      badge: countBadge(items.length),
    },
    {
      id: 'locations' as const,
      label: t('site_inventory.tab_locations', { defaultValue: 'Locations' }),
      icon: <Warehouse size={15} />,
      badge: countBadge(locations.length),
    },
  ];

  const headerAction =
    activeTab === 'items' ? (
      <Button variant="primary" size="sm" icon={<Plus size={14} />} onClick={() => setShowItemModal(true)}>
        {t('site_inventory.new_item', { defaultValue: 'New item' })}
      </Button>
    ) : activeTab === 'locations' ? (
      <Button
        variant="primary"
        size="sm"
        icon={<Plus size={14} />}
        onClick={() => setShowLocationModal(true)}
      >
        {t('site_inventory.new_location', { defaultValue: 'New location' })}
      </Button>
    ) : (
      <Button
        variant="primary"
        size="sm"
        icon={<Plus size={14} />}
        onClick={() => setShowMovementModal(true)}
        disabled={items.length === 0}
        title={
          items.length === 0
            ? t('site_inventory.add_item_first', {
                defaultValue: 'Add a stock item before recording a movement',
              })
            : undefined
        }
      >
        {t('site_inventory.record_movement', { defaultValue: 'Record movement' })}
      </Button>
    );

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        srTitle={t('site_inventory.title', { defaultValue: 'Site Inventory' })}
        subtitle={t('site_inventory.subtitle', {
          defaultValue: 'Track on-site material stock, storage locations and every stock movement',
        })}
        actions={headerAction}
      />

      <RequiresProject
        emptyHint={t('site_inventory.select_project', {
          defaultValue: 'Open a project first to view and manage site inventory.',
        })}
      >
        <TabBar<TabId>
          tabs={tabs}
          activeId={activeTab}
          onChange={(id) => setActiveTab(id)}
          ariaLabel={t('site_inventory.tabs_aria', { defaultValue: 'Site inventory sections' })}
          variant="underline"
        />

        <div role="tabpanel">
          {activeTab === 'stock' && (
            <StockPanel
              query={stockQuery}
              rows={stockRows}
              summary={stockSummary}
              status={balanceStatus}
            />
          )}
          {activeTab === 'movements' && (
            <MovementsPanel
              query={movementsQuery}
              movements={movements}
              itemName={itemName}
              itemsById={itemsById}
              locName={locName}
              onRecord={() => setShowMovementModal(true)}
              canRecord={items.length > 0}
            />
          )}
          {activeTab === 'items' && (
            <ItemsPanel query={itemsQuery} items={items} onCreate={() => setShowItemModal(true)} />
          )}
          {activeTab === 'locations' && (
            <LocationsPanel
              query={locationsQuery}
              locations={locations}
              onCreate={() => setShowLocationModal(true)}
            />
          )}
        </div>
      </RequiresProject>

      {showMovementModal && (
        <RecordMovementModal
          items={items}
          locations={locations}
          onClose={() => setShowMovementModal(false)}
          onSubmit={(data) => movementMut.mutate(data)}
          isPending={movementMut.isPending}
        />
      )}
      {showItemModal && (
        <CreateItemModal
          locations={locations}
          onClose={() => setShowItemModal(false)}
          onSubmit={(data) => itemMut.mutate(data)}
          isPending={itemMut.isPending}
        />
      )}
      {showLocationModal && (
        <CreateLocationModal
          onClose={() => setShowLocationModal(false)}
          onSubmit={(data) => locationMut.mutate(data)}
          isPending={locationMut.isPending}
        />
      )}
    </div>
  );
}

/* -- Panels ---------------------------------------------------------------- */

interface QueryLike {
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
}

const thCls = 'px-4 py-2.5 text-left font-medium';
const tdCls = 'px-4 py-3 text-content-primary';

const STATUS_BADGE: Record<BalanceStatus, { variant: BadgeVariant; key: string; def: string }> = {
  negative: { variant: 'error', key: 'site_inventory.status_negative', def: 'Negative' },
  low: { variant: 'warning', key: 'site_inventory.status_low', def: 'Low stock' },
  ok: { variant: 'success', key: 'site_inventory.status_ok', def: 'In stock' },
};

function StockPanel({
  query,
  rows,
  summary,
  status,
}: {
  query: QueryLike;
  rows: StockOnHandRow[];
  summary: { tracked: number; low: number; negative: number };
  status: (row: StockOnHandRow) => BalanceStatus;
}) {
  const { t } = useTranslation();
  if (query.isLoading) return <SkeletonTable rows={5} columns={4} />;
  if (query.isError) return <InlineError error={query.error} onRetry={query.refetch} />;
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<Boxes size={28} strokeWidth={1.5} />}
        title={t('site_inventory.no_stock', { defaultValue: 'No stock on hand yet' })}
        description={t('site_inventory.no_stock_hint', {
          defaultValue: 'Record an inbound movement to start metering material stock.',
        })}
      />
    );
  }

  const chips: { key: string; def: string; value: number; tone: string }[] = [
    { key: 'site_inventory.stat_tracked', def: 'Items tracked', value: summary.tracked, tone: 'text-content-primary' },
    { key: 'site_inventory.stat_low', def: 'Low stock', value: summary.low, tone: 'text-amber-500' },
    { key: 'site_inventory.stat_negative', def: 'Negative', value: summary.negative, tone: 'text-semantic-error' },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        {chips.map((c) => (
          <div key={c.key} className="rounded-xl border border-border-light bg-surface-elevated/90 p-4">
            <p className="text-2xs font-medium text-content-tertiary uppercase tracking-wide">
              {t(c.key, { defaultValue: c.def })}
            </p>
            <p className={clsx('text-lg font-semibold mt-1 tabular-nums', c.tone)}>{c.value}</p>
          </div>
        ))}
      </div>
      <Card padding="none" className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border-light bg-surface-secondary/30 text-2xs uppercase tracking-wider text-content-tertiary">
              <th className={thCls}>{t('site_inventory.col_item', { defaultValue: 'Item' })}</th>
              <th className={thCls}>{t('site_inventory.col_unit', { defaultValue: 'Unit' })}</th>
              <th className={clsx(thCls, 'text-right')}>
                {t('site_inventory.col_on_hand', { defaultValue: 'On hand' })}
              </th>
              <th className={clsx(thCls, 'text-center')}>
                {t('site_inventory.col_status', { defaultValue: 'Status' })}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const st = status(row);
              const badge = STATUS_BADGE[st];
              return (
                <tr
                  key={row.item_id}
                  className="border-b border-border-light last:border-0 hover:bg-surface-secondary/40"
                >
                  <td className={clsx(tdCls, 'font-medium')}>{row.name}</td>
                  <td className={clsx(tdCls, 'text-content-tertiary')}>{row.unit || '-'}</td>
                  <td
                    className={clsx(
                      tdCls,
                      'text-right tabular-nums font-semibold',
                      st === 'negative' && 'text-semantic-error',
                    )}
                  >
                    {row.on_hand}
                  </td>
                  <td className={clsx(tdCls, 'text-center')}>
                    <Badge variant={badge.variant} size="sm" dot>
                      {t(badge.key, { defaultValue: badge.def })}
                    </Badge>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function MovementsPanel({
  query,
  movements,
  itemName,
  itemsById,
  locName,
  onRecord,
  canRecord,
}: {
  query: QueryLike;
  movements: StockMovement[];
  itemName: (id: string) => string;
  itemsById: Map<string, StockItem>;
  locName: (id: string | null) => string;
  onRecord: () => void;
  canRecord: boolean;
}) {
  const { t } = useTranslation();
  if (query.isLoading) return <SkeletonTable rows={5} columns={6} />;
  if (query.isError) return <InlineError error={query.error} onRetry={query.refetch} />;
  if (movements.length === 0) {
    return (
      <EmptyState
        icon={<ArrowLeftRight size={28} strokeWidth={1.5} />}
        title={t('site_inventory.no_movements', { defaultValue: 'No movements yet' })}
        description={t('site_inventory.no_movements_hint', {
          defaultValue: 'Record the first stock movement to build the ledger.',
        })}
        action={
          canRecord
            ? {
                label: t('site_inventory.record_movement', { defaultValue: 'Record movement' }),
                onClick: onRecord,
              }
            : undefined
        }
      />
    );
  }

  return (
    <Card padding="none" className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border-light bg-surface-secondary/30 text-2xs uppercase tracking-wider text-content-tertiary">
            <th className={thCls}>{t('site_inventory.col_date', { defaultValue: 'Date' })}</th>
            <th className={thCls}>{t('site_inventory.col_type', { defaultValue: 'Type' })}</th>
            <th className={thCls}>{t('site_inventory.col_item', { defaultValue: 'Item' })}</th>
            <th className={clsx(thCls, 'text-right')}>
              {t('site_inventory.col_quantity', { defaultValue: 'Quantity' })}
            </th>
            <th className={thCls}>{t('site_inventory.col_location', { defaultValue: 'Location' })}</th>
            <th className={thCls}>{t('site_inventory.col_note', { defaultValue: 'Note' })}</th>
          </tr>
        </thead>
        <tbody>
          {movements.map((m) => {
            const cfg = MOVEMENT_TYPE_CONFIG[m.movement_type];
            const Icon = cfg.icon;
            const unit = itemsById.get(m.item_id)?.unit ?? '';
            const locationCell =
              m.movement_type === 'TRANSFER' && m.to_location_id
                ? t('site_inventory.transfer_route', {
                    defaultValue: '{{from}} to {{to}}',
                    from: locName(m.location_id),
                    to: locName(m.to_location_id),
                  })
                : locName(m.location_id) || '-';
            return (
              <tr
                key={m.id}
                className="border-b border-border-light last:border-0 hover:bg-surface-secondary/40"
              >
                <td className={clsx(tdCls, 'whitespace-nowrap text-content-tertiary')}>
                  <DateDisplay value={m.occurred_at} />
                </td>
                <td className={tdCls}>
                  <Badge variant={cfg.variant} size="sm">
                    <Icon size={12} className="mr-1" />
                    {t(`site_inventory.movement_type_${m.movement_type.toLowerCase()}`, {
                      defaultValue: MOVEMENT_TYPE_LABEL[m.movement_type],
                    })}
                  </Badge>
                </td>
                <td className={clsx(tdCls, 'font-medium')}>{itemName(m.item_id)}</td>
                <td className={clsx(tdCls, 'text-right tabular-nums')}>
                  {m.quantity}
                  {unit ? ` ${unit}` : ''}
                </td>
                <td className={clsx(tdCls, 'text-content-tertiary')}>{locationCell}</td>
                <td className={clsx(tdCls, 'text-content-tertiary max-w-[16rem] truncate')}>
                  {m.note || '-'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

function ItemsPanel({
  query,
  items,
  onCreate,
}: {
  query: QueryLike;
  items: StockItem[];
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  if (query.isLoading) return <SkeletonTable rows={5} columns={6} />;
  if (query.isError) return <InlineError error={query.error} onRetry={query.refetch} />;
  if (items.length === 0) {
    return (
      <EmptyState
        icon={<Package size={28} strokeWidth={1.5} />}
        title={t('site_inventory.no_items', { defaultValue: 'No stock items yet' })}
        description={t('site_inventory.no_items_hint', {
          defaultValue: 'Add the materials you want to meter on site.',
        })}
        action={{
          label: t('site_inventory.new_item', { defaultValue: 'New item' }),
          onClick: onCreate,
        }}
      />
    );
  }

  return (
    <Card padding="none" className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border-light bg-surface-secondary/30 text-2xs uppercase tracking-wider text-content-tertiary">
            <th className={thCls}>{t('site_inventory.col_item', { defaultValue: 'Item' })}</th>
            <th className={thCls}>{t('site_inventory.col_sku', { defaultValue: 'SKU' })}</th>
            <th className={thCls}>{t('site_inventory.col_unit', { defaultValue: 'Unit' })}</th>
            <th className={clsx(thCls, 'text-right')}>
              {t('site_inventory.col_unit_cost', { defaultValue: 'Unit cost' })}
            </th>
            <th className={clsx(thCls, 'text-right')}>
              {t('site_inventory.col_reorder', { defaultValue: 'Reorder point' })}
            </th>
            <th className={clsx(thCls, 'text-center')}>
              {t('site_inventory.col_active', { defaultValue: 'Active' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr
              key={it.id}
              className="border-b border-border-light last:border-0 hover:bg-surface-secondary/40"
            >
              <td className={clsx(tdCls, 'font-medium')}>{it.name}</td>
              <td className={clsx(tdCls, 'text-content-tertiary')}>{it.sku || '-'}</td>
              <td className={clsx(tdCls, 'text-content-tertiary')}>{it.unit || '-'}</td>
              <td className={clsx(tdCls, 'text-right tabular-nums')}>
                {it.standard_unit_cost
                  ? `${it.standard_unit_cost}${it.currency ? ` ${it.currency}` : ''}`
                  : '-'}
              </td>
              <td className={clsx(tdCls, 'text-right tabular-nums')}>{it.reorder_point ?? '-'}</td>
              <td className={clsx(tdCls, 'text-center')}>
                <Badge variant={it.is_active ? 'success' : 'neutral'} size="sm">
                  {it.is_active
                    ? t('site_inventory.active_yes', { defaultValue: 'Yes' })
                    : t('site_inventory.active_no', { defaultValue: 'No' })}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function LocationsPanel({
  query,
  locations,
  onCreate,
}: {
  query: QueryLike;
  locations: StockLocation[];
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  if (query.isLoading) return <SkeletonTable rows={4} columns={4} />;
  if (query.isError) return <InlineError error={query.error} onRetry={query.refetch} />;
  if (locations.length === 0) {
    return (
      <EmptyState
        icon={<Warehouse size={28} strokeWidth={1.5} />}
        title={t('site_inventory.no_locations', { defaultValue: 'No storage locations yet' })}
        description={t('site_inventory.no_locations_hint', {
          defaultValue: 'Add a yard, container or store so stock can be located.',
        })}
        action={{
          label: t('site_inventory.new_location', { defaultValue: 'New location' }),
          onClick: onCreate,
        }}
      />
    );
  }

  return (
    <Card padding="none" className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border-light bg-surface-secondary/30 text-2xs uppercase tracking-wider text-content-tertiary">
            <th className={thCls}>{t('site_inventory.col_name', { defaultValue: 'Name' })}</th>
            <th className={thCls}>{t('site_inventory.col_code', { defaultValue: 'Code' })}</th>
            <th className={thCls}>{t('site_inventory.col_address', { defaultValue: 'Address' })}</th>
            <th className={clsx(thCls, 'text-center')}>
              {t('site_inventory.col_active', { defaultValue: 'Active' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {locations.map((loc) => (
            <tr
              key={loc.id}
              className="border-b border-border-light last:border-0 hover:bg-surface-secondary/40"
            >
              <td className={clsx(tdCls, 'font-medium')}>{loc.name}</td>
              <td className={clsx(tdCls, 'text-content-tertiary')}>{loc.code || '-'}</td>
              <td className={clsx(tdCls, 'text-content-tertiary')}>{loc.address || '-'}</td>
              <td className={clsx(tdCls, 'text-center')}>
                <Badge variant={loc.is_active ? 'success' : 'neutral'} size="sm">
                  {loc.is_active
                    ? t('site_inventory.active_yes', { defaultValue: 'Yes' })
                    : t('site_inventory.active_no', { defaultValue: 'No' })}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
