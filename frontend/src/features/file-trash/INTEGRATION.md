# W2 — Recycle Bin Integration

Splice instructions for wiring the `file-trash` feature into the
existing file-manager UI. Do NOT modify the shared file-manager
files directly — paste these snippets in the marked locations.

## 1. `BulkActionsBar.tsx` — convert delete from hard-delete to soft-delete

**File**: `frontend/src/features/file-manager/components/BulkActionsBar.tsx`

The current implementation hard-deletes via per-kind endpoints
(`bulkDeleteDocuments`, `deleteByKind`). Replace the mutation with
the soft-delete flow that snapshots into the recycle bin and shows
an undo toast.

### Add imports (top of file, near line 21)

```tsx
import { useSoftDelete, useRestoreFromTrash } from '@/features/file-trash/hooks';
import { showUndoDeleteToast } from '@/features/file-trash/UndoDeleteToast';
import type { TrashKind } from '@/features/file-trash/types';
```

### Replace the existing `dispatchBulkDelete` with a soft-delete version

The function definition is around lines 69-133. Keep `groupByKind`
as-is. Replace the body of `dispatchBulkDelete` so each id flows
through `softDelete` (POST `/file-trash/`) instead of the per-kind
DELETE endpoint:

```tsx
import { softDelete } from '@/features/file-trash/api';

export async function dispatchBulkDelete(
  rows: FileRow[],
  projectId: string,
): Promise<DispatchSummary> {
  const groups = groupByKind(rows);
  const perKind: PerKindResult[] = [];
  const trashIds: { id: string; name: string; trashId: string }[] = [];

  for (const [kind, items] of groups) {
    const ids = items.map((r) => r.id);
    const results = await Promise.allSettled(
      items.map((row) =>
        softDelete({
          project_id: projectId,
          kind: kind as TrashKind,
          original_id: row.id,
          canonical_name: row.name,
        }),
      ),
    );
    const failed: { id: string; message: string }[] = [];
    results.forEach((res, idx) => {
      if (res.status === 'rejected') {
        failed.push({
          id: ids[idx]!,
          message: res.reason instanceof Error ? res.reason.message : String(res.reason),
        });
      } else {
        trashIds.push({
          id: ids[idx]!,
          name: items[idx]!.name,
          trashId: res.value.id,
        });
      }
    });
    perKind.push({
      kind,
      requested: ids.length,
      deleted: ids.length - failed.length,
      failed,
    });
  }

  const total = perKind.reduce((acc, r) => acc + r.requested, 0);
  const deleted = perKind.reduce((acc, r) => acc + r.deleted, 0);
  const failed = perKind.reduce((acc, r) => acc + r.failed.length, 0);
  return { total, deleted, failed, perKind, trashIds };
}
```

(Add `trashIds: { id: string; name: string; trashId: string }[]`
to the `DispatchSummary` interface.)

### Wire the undo toast inside the component's `onSuccess`

The `useMutation` block is around lines 144-192. Replace its
`onSuccess` so it fires `showUndoDeleteToast` for each
successfully-trashed file. Bind the restore mutation once at the
top of the component:

```tsx
const restoreMutation = useRestoreFromTrash(projectId);

const deleteMutation = useMutation({
  mutationFn: async (rows: FileRow[]) => dispatchBulkDelete(rows, projectId),
  onSuccess: (summary: DispatchSummary) => {
    queryClient.invalidateQueries({ queryKey: [fileManagerKeys.tree, projectId] });
    queryClient.invalidateQueries({ queryKey: [fileManagerKeys.list, projectId] });

    // Single-file delete → single undo toast.
    if (summary.trashIds.length === 1) {
      const only = summary.trashIds[0]!;
      showUndoDeleteToast({
        fileName: only.name,
        trashId: only.trashId,
        onUndo: (tid) => restoreMutation.mutate(tid),
        t,
      });
    } else if (summary.trashIds.length > 1) {
      addToast({
        type: 'info',
        title: t('files.trash.bulk_deleted', {
          defaultValue: '{{count}} file(s) moved to Recycle Bin',
          count: summary.trashIds.length,
        }),
        message: t('files.trash.bulk_deleted_hint', {
          defaultValue: 'Open the Recycle Bin to restore individual files.',
        }),
      });
    }

    // Existing partial-failure / total-failure toasts stay; just
    // chain the trash toast above them.
    setConfirming(false);
    onClear();
  },
  // ...existing onError unchanged
});
```

## 2. `FileTree.tsx` — add the Trash node under the categories

**File**: `frontend/src/features/file-manager/components/FileTree.tsx`

### Add the import (top of file, around line 4)

```tsx
import { TrashNode } from '@/features/file-trash/TrashNode';
```

### Mount the trash node after the main categories list

The component returns an `<aside>` containing the storage strip,
the categories panel, etc. Add the trash node at the very bottom
of the aside, just inside the closing tag (and pass the active
project id through props — see below).

You will need to thread `projectId` into `FileTreeProps`. The
current props only carry `nodes` / `selectedId` / `onSelect` /
`isLoading` — add an optional `projectId?: string | null` field.

Append, after the last child element of the aside:

```tsx
<div className="mt-2 px-3 pb-3 border-t border-border-light pt-2">
  <TrashNode projectId={projectId} active={selectedId === 'trash'} />
</div>
```

## 3. `FileManagerPage.tsx` — route to `/files/trash` for the dedicated page

**File**: `frontend/src/features/file-manager/FileManagerPage.tsx`

The recycle bin lives at its own route, not as an inline view of
the file manager. Two integration points:

### a) Pass `projectId` to `FileTree`

Around the existing `<FileTree ... />` call, add `projectId={projectId}`.

### b) Register the route in `frontend/src/app/App.tsx`

Add a lazy import next to the existing `FileManagerPage` lazy
(around line 178):

```tsx
const TrashPage = lazy(() =>
  import('@/features/file-trash/TrashPage').then((m) => ({ default: m.TrashPage })),
);
```

Add the route inside the same `<Routes>` block where `/files` is
mounted (around line 535):

```tsx
<Route path="/files/trash" element={<P title="Recycle Bin"><TrashPage /></P>} />
```

This must come BEFORE `/files/:something` style parametric routes
to avoid the route-shadowing trap.

## 4. Translation keys to merge

```json
{
  "files": {
    "trash": {
      "title": "Recycle Bin",
      "sidebar_title": "Recycle Bin",
      "sidebar_label": "Recycle Bin",
      "count_aria": "{{count}} items in recycle bin",
      "summary": "{{count}} item(s) · {{bytes}}",
      "back_to_files": "Back to files",
      "no_project_title": "Select a project first",
      "no_project_desc": "The Recycle Bin is scoped to one project at a time. Open a project from /files to see its trashed files.",
      "empty_title": "Recycle Bin is empty",
      "empty_description": "Deleted files appear here for 30 days before they are permanently removed.",
      "load_failed": "Could not load the Recycle Bin. Please try again.",
      "trashed_label": "Trashed",
      "days_left": "{{n}}d left",
      "restore": "Restore",
      "restored_title": "Restored: {{name}}",
      "restore_failed_title": "Could not restore file",
      "purge": "Delete forever",
      "confirm_purge": "Confirm",
      "purged_title": "Permanently deleted: {{name}}",
      "purge_failed_title": "Could not purge file",
      "bulk_deleted": "{{count}} file(s) moved to Recycle Bin",
      "bulk_deleted_hint": "Open the Recycle Bin to restore individual files.",
      "toast": {
        "deleted_title": "Moved to Recycle Bin",
        "deleted_message": "{{name}} can be restored within 30 days.",
        "undo": "Undo"
      }
    },
    "kind": {
      "document": "Document",
      "photo": "Photo",
      "sheet": "Sheet",
      "bim_model": "BIM model",
      "dwg_drawing": "DWG drawing",
      "takeoff": "Takeoff",
      "report": "Report",
      "markup": "Markup"
    }
  }
}
```

## 5. Nightly purge — Celery / cron wiring

The hard-purge function is `purge_expired_trash` in
`backend/app/modules/file_trash/service.py`. It is async + takes a
session; wire it into the existing scheduler (Celery beat or a
plain `apscheduler` job) on a daily cadence. Do NOT call it from
the request lifecycle.

Example Celery task body:

```python
from app.database import async_session_factory
from app.modules.file_trash.service import purge_expired_trash

async def _run() -> None:
    async with async_session_factory() as session:
        await purge_expired_trash(session)
        await session.commit()
```
