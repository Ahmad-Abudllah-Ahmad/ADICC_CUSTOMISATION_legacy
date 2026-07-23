# File Tags (W4) — Integration Instructions

This feature ships independently from the shared file-manager UI. Splice the
following snippets into the shared files to wire it in. **Do not modify the
shared files yourself** — these are the exact splices a maintainer should
make.

## 1. `FileActionsBar.tsx` — Add the tag filter facet

**File:** `frontend/src/features/file-manager/components/FileActionsBar.tsx`

### 1a. Add the import

```tsx
import { TagFilterFacet } from '@/features/file-tags/TagFilterFacet';
```

### 1b. Extend the props interface

```tsx
interface FileActionsBarProps {
  // ...existing props
  projectId: string;
  selectedTagIds?: string[];
  onSelectedTagsChange?: (tagIds: string[]) => void;
}
```

### 1c. Splice the facet inside the `ms-auto` flex group

Around line 141 (`<div className="ms-auto flex items-center gap-2">`), as
the FIRST child of that wrapper, splice:

```tsx
{onSelectedTagsChange && (
  <TagFilterFacet
    projectId={projectId}
    selectedTagIds={selectedTagIds ?? []}
    onChange={onSelectedTagsChange}
  />
)}
```

This sits next to the existing Sort dropdown so the toolbar layout stays
balanced.

## 2. `FileManagerPage.tsx` — Hold tag filter state

**File:** `frontend/src/features/file-manager/FileManagerPage.tsx`

### 2a. Add state next to the other filter state

```tsx
const [selectedTagIds, setSelectedTagIds] = useState<string[]>([]);
```

### 2b. Pass it into `FileActionsBar`

```tsx
<FileActionsBar
  /* ...existing props */
  projectId={projectId}
  selectedTagIds={selectedTagIds}
  onSelectedTagsChange={setSelectedTagIds}
/>
```

### 2c. Client-side filtering (until the backend supports `?tag=`)

```tsx
import { fetchTagsForFile } from '@/features/file-tags/api';
// or, for the list view, use a single bulk call:
import { useTagsByFile } from '@/features/file-tags/hooks';
```

Filter the `items` array before passing to `FileGrid` / `FileList`:

```tsx
const filteredItems = useMemo(() => {
  if (selectedTagIds.length === 0) return items;
  // Tag rows are loaded lazily per visible row (see step 4), so the
  // filter is best applied AFTER hydrating tag membership. Use the
  // local map you already built for FileGrid badge rendering.
  return items.filter((row) =>
    selectedTagIds.every((id) => tagMap[row.id]?.some((t) => t.id === id)),
  );
}, [items, selectedTagIds, tagMap]);
```

## 3. `BulkActionsBar.tsx` — Add the "Tag selected" button

**File:** `frontend/src/features/file-manager/components/BulkActionsBar.tsx`

### 3a. Add the imports

```tsx
import { Tag } from 'lucide-react';
import { useState } from 'react';
import { BulkTagDrawer } from '@/features/file-tags/BulkTagDrawer';
```

### 3b. Inside the component:

```tsx
const [tagDrawerOpen, setTagDrawerOpen] = useState(false);
```

### 3c. Splice a button next to the existing Delete button (the
`<div className="ms-auto flex items-center gap-2">` block at line ~213):

```tsx
<button
  type="button"
  onClick={() => setTagDrawerOpen(true)}
  className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium border border-border-light text-content-secondary hover:bg-surface-secondary"
>
  <Tag size={13} />
  {t('files.tags.bulk.button', { defaultValue: 'Tag selected' })}
</button>
```

### 3d. At the end of the component (just before the closing `</div>`):

```tsx
<BulkTagDrawer
  open={tagDrawerOpen}
  onClose={() => setTagDrawerOpen(false)}
  projectId={projectId}
  selectedRows={selectedRows.map((r) => ({ id: r.id, kind: r.kind }))}
/>
```

## 4. `FileGrid.tsx` — Render `TagPill` under each tile

**File:** `frontend/src/features/file-manager/components/FileGrid.tsx`

### 4a. Add the imports

```tsx
import { TagPill } from '@/features/file-tags/TagPill';
import { useTagsByFile } from '@/features/file-tags/hooks';
```

### 4b. Inside the `items.map((row) => { ... })`, after the existing
`<div className="mt-1 flex items-center justify-between text-[10px]...">`
block (around line 146), splice a tags row:

```tsx
<FileGridTagsRow projectId={row.project_id} kind={row.kind} fileId={row.id} />
```

### 4c. Define the helper at module scope (under `fmtBytes`):

```tsx
function FileGridTagsRow({
  projectId,
  kind,
  fileId,
}: {
  projectId: string;
  kind: FileKind;
  fileId: string;
}) {
  const { data: tags } = useTagsByFile(projectId, kind, fileId);
  if (!tags || tags.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-0.5">
      {tags.slice(0, 3).map((tag) => (
        <TagPill key={tag.id} tag={tag} size="sm" />
      ))}
      {tags.length > 3 && (
        <span className="text-[9px] text-content-tertiary tabular-nums">
          +{tags.length - 3}
        </span>
      )}
    </div>
  );
}
```

> **N+1 mitigation:** in production we recommend swapping the per-row
> hook for a single `tagsByFiles` query in `FileManagerPage` and passing
> the lookup down via props/context — see the `tags_by_files` service
> helper on the backend, which already supports bulk lookup. The per-row
> hook is fine for ≤ 50 tiles per page.

## 5. `FileList.tsx` — Render `TagPill` row under each list row

**File:** `frontend/src/features/file-manager/components/FileList.tsx`

Same idea as FileGrid — splice a `<FileListTagsCell>` cell inside each
row's metadata column:

```tsx
import { TagPill } from '@/features/file-tags/TagPill';
import { useTagsByFile } from '@/features/file-tags/hooks';
```

And inside the row template:

```tsx
<FileListTagsCell projectId={row.project_id} kind={row.kind} fileId={row.id} />
```

Helper:

```tsx
function FileListTagsCell({
  projectId,
  kind,
  fileId,
}: {
  projectId: string;
  kind: FileKind;
  fileId: string;
}) {
  const { data: tags } = useTagsByFile(projectId, kind, fileId);
  if (!tags || tags.length === 0) return null;
  return (
    <span className="inline-flex flex-wrap gap-0.5 ms-2">
      {tags.slice(0, 4).map((tag) => (
        <TagPill key={tag.id} tag={tag} size="sm" />
      ))}
    </span>
  );
}
```

## New translation keys

Add to `frontend/src/app/locales/en.ts` (mirror in other locales):

```ts
'files.tags.filter_label': 'Tags',
'files.tags.filter_label_count': 'Tags · {{count}}',
'files.tags.no_tags': 'No tags in this project yet.',
'files.tags.clear_filter': 'Clear filter',
'files.tags.category.discipline': 'Discipline',
'files.tags.category.phase': 'Phase',
'files.tags.category.package': 'Package',
'files.tags.category.custom': 'Custom',
'files.tags.uncategorized': 'Other',
'files.tags.picker_title': 'Choose tags',
'files.tags.filter_placeholder': 'Filter tags…',
'files.tags.new_name': 'New tag name',
'files.tags.new_tag': 'New tag…',
'files.tags.create': 'Create',
'files.tags.save': 'Save tags',
'files.tags.remove': 'Remove tag {{tag}}',
'files.tags.bulk.button': 'Tag selected',
'files.tags.bulk.title': 'Tag {{count}} file(s)',
'files.tags.bulk.add_tags': 'Add tags…',
'files.tags.bulk.remove_tags': 'Remove tags…',
'files.tags.bulk.assigned': '{{count}} assignment(s) created',
'files.tags.bulk.unassigned': '{{count}} assignment(s) removed',
'files.tags.bulk.partial': '{{changed}} succeeded, {{failed}} failed',
'files.tags.bulk.picker_assign': 'Add tags to selected files',
'files.tags.bulk.picker_unassign': 'Remove tags from selected files',
'files.tags.bulk.drawer_label': 'Bulk tag operations',
```

## API summary (for backend deploy notes)

| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/v1/file-tags/?project_id=` | `file_tags.read` |
| POST | `/api/v1/file-tags/` | `file_tags.write` |
| PATCH | `/api/v1/file-tags/{id}/?project_id=` | `file_tags.write` |
| DELETE | `/api/v1/file-tags/{id}/?project_id=` | `file_tags.write` |
| POST | `/api/v1/file-tags/{id}/assign/?project_id=` | `file_tags.assign` |
| POST | `/api/v1/file-tags/{id}/unassign/?project_id=` | `file_tags.assign` |
| GET | `/api/v1/file-tags/by-file/?project_id=&kind=&file_id=` | `file_tags.read` |
| POST | `/api/v1/file-tags/seed-defaults/?project_id=` | `file_tags.write` |

The migration is `backend/alembic/versions/v3061_file_search_tags.py`. It
creates `oe_file_tag` + `oe_file_tag_assignment` alongside the search
index table. Run `alembic upgrade head` to apply.

## Seeding AECO defaults for a new project

Hook the `useSeedDefaultTags()` mutation into the project-creation flow
(e.g. inside `useCreateProject`'s `onSuccess`). The seed is idempotent —
re-calling it on an existing project is a no-op, and existing
custom tags are never overwritten.

```tsx
const seedTags = useSeedDefaultTags();
// inside the project-creation success path:
seedTags.mutate(newProject.id);
```
