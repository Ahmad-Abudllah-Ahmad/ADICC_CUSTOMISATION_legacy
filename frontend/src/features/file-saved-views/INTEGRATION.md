# Integrating file-saved-views into the file manager (Wave W5)

This module is **side-mountable**: the existing `file-manager` feature
does not need to know that saved views exist. All wiring lives in
three small splices that the file-manager owner can apply.

## 1. Add SavedViewsRail under the FileTree kind list

**File**: `frontend/src/features/file-manager/components/FileTree.tsx`

Add the import near the top:

```ts
import { SavedViewsRail } from '@/features/file-saved-views';
```

Inside the `FileTree` component, render the rail directly under the
existing kind list. The recommended location is at the very bottom of
the component's root container — keep it inside the same scroll
parent so it shares the sidebar's vertical layout:

```tsx
// ── existing kind list above ──

{projectId && (
  <div className="border-t border-border-light pt-2 mt-2">
    <SavedViewsRail projectId={projectId} />
  </div>
)}
```

`FileTree` is documented as not-to-be-modified, so the splice is the
**only** change required and it is purely additive — no existing
props, JSX or styles are touched.

If `FileTree.tsx` does not currently receive `projectId`, lift it
through the existing `FileManagerPage` props (read from
`useSearchParams().get('project')`) and pass it down. The component
remains backward-compatible: when `projectId` is null the rail still
mounts but lists only the user's global views (those with
`project_id IS NULL`).

## 2. Add SaveViewButton to the FileActionsBar

**File**: `frontend/src/features/file-manager/components/FileActionsBar.tsx`

Imports:

```ts
import { SaveViewButton } from '@/features/file-saved-views';
import type { FilterSnapshot } from '@/features/file-saved-views';
```

Render the pill at the end of the actions row, gated on "filter is
non-default":

```tsx
const filterIsNonDefault =
  Boolean(filters.q) ||
  Boolean(filters.category) ||
  Boolean(filters.extension) ||
  (filters.sort && filters.sort !== 'modified');

const filterSnapshot: FilterSnapshot = {
  kind: filters.category ?? null,
  q: filters.q ?? null,
  sort: filters.sort ?? null,
  extension: filters.extension ?? null,
};

// inside the JSX, at the end of the actions row:
<SaveViewButton
  projectId={projectId}
  filter={filterSnapshot}
  visible={filterIsNonDefault}
/>
```

The button only renders when the user has actually narrowed the file
list — the default unfiltered state never offers "Save view" because
that would clutter the rail with empty filters.

## 3. URL → filter restoration (existing FileManagerPage)

`SavedViewsRail` already navigates to
`/files?kind=...&q=...&sort=...&extension=...` when a view is
applied. The existing `FileManagerPage` should read these query
params on mount and seed its filter state from them — no further
changes needed if it already does (it already supports `?project=`
and other query keys per the production routing).

If `FileManagerPage` does NOT yet read those keys, add:

```ts
const [searchParams] = useSearchParams();
const initialFilters: FileFilters = {
  category: (searchParams.get('kind') as FileKind | null) ?? undefined,
  q: searchParams.get('q') ?? undefined,
  sort: (searchParams.get('sort') as FileFilters['sort']) ?? undefined,
  extension: searchParams.get('extension') ?? undefined,
};
```

## 4. New translation keys

All UI strings expose a `defaultValue` fallback, so the feature works
without any translation work. To override or localise:

| Key                                       | English fallback                                     |
| ----------------------------------------- | ---------------------------------------------------- |
| `files.views.title`                       | Saved views                                          |
| `files.views.loading`                     | Loading…                                             |
| `files.views.empty`                       | No saved views yet                                   |
| `files.views.shared_label`                | Shared                                               |
| `files.views.save_button`                 | Save view                                            |
| `files.views.dialog_title`                | Save current filter as view                          |
| `files.views.dialog_subtitle`             | Re-apply this filter from the saved-views rail …     |
| `files.views.dialog_name_label`           | Name                                                 |
| `files.views.dialog_name_placeholder`     | e.g. Structural drawings for review                  |
| `files.views.dialog_icon_label`           | Icon                                                 |
| `files.views.dialog_pin`                  | Pin to top of rail                                   |
| `files.views.dialog_share`                | Share with everyone on this project                  |
| `files.views.dialog_save`                 | Save view                                            |
| `files.views.error_name_required`         | Name is required                                     |
| `files.views.action_rename`               | Rename                                               |
| `files.views.action_pin` / `action_unpin` | Pin / Unpin                                          |
| `files.views.action_share` / `_unshare`   | Share with project / Stop sharing                    |
| `files.views.action_duplicate`            | Duplicate                                            |
| `files.views.action_delete`               | Delete                                               |
| `files.views.rename_prompt`               | New name                                             |
| `files.views.delete_confirm`              | Delete saved view "{{name}}"?                        |

## Public surface

```ts
import {
  SavedViewsRail,
  SaveViewButton,
  SaveViewDialog,
  useSavedViews,
  useApplyView,
  useCreateView,
  useUpdateView,
  useDeleteView,
  useDuplicateView,
  serializeFilter,
  type SavedViewResponse,
  type FilterSnapshot,
} from '@/features/file-saved-views';
```
