# W1 — File Versioning Integration

Splice instructions for wiring the `file-versions` feature into the
existing file-manager UI. Do NOT modify the shared file-manager
files directly — paste these snippets in the marked locations.

## 1. `FilePreviewPane.tsx` — add the version dropdown above secondary actions

**File**: `frontend/src/features/file-manager/components/FilePreviewPane.tsx`

### Add the import (near the other lucide / local imports, around line 13)

```tsx
import { VersionDropdown } from '@/features/file-versions/VersionDropdown';
```

### Mount the dropdown above the secondary actions strip

The component currently renders a flex column of primary + secondary
buttons starting at the `<div className="flex flex-col gap-1.5">` block
(around line 185 — the block that begins with the "Primary action"
comment). Add the dropdown directly above the **Email link** button
(currently around line 246, just after the **Download** link):

Locate this block (around line 233–250):

```tsx
{row.download_url && (
  <a
    href={row.download_url}
    ...
  >
    <Download size={13} />
    {t('files.actions.download', { defaultValue: 'Download' })}
  </a>
)}
<button
  type="button"
  onClick={() => onEmail(row)}
  ...
>
  <Mail size={13} />
  {t('files.actions.email', { defaultValue: 'Email link' })}
</button>
```

Insert a one-line strip between the Download anchor and the Email
button:

```tsx
{row.download_url && (
  <a href={row.download_url} ...>
    <Download size={13} />
    {t('files.actions.download', { defaultValue: 'Download' })}
  </a>
)}

{/* W1 — version history. Renders ``<V## · Current>`` chip + drop-
    down with a "Make current" action for every superseded row in
    the chain. */}
<div className="flex items-center justify-between gap-2 px-1 py-1 border-y border-border-light/60">
  <span className="text-[10px] uppercase tracking-wider text-content-tertiary font-medium">
    {t('files.versions.section_label', { defaultValue: 'Versions' })}
  </span>
  <VersionDropdown fileId={row.id} kind={row.kind} />
</div>

<button type="button" onClick={() => onEmail(row)} ...>
  ...
</button>
```

## 2. Translation keys to merge

Add the following keys to every locale dictionary you ship (only
the English entries are listed; provide localized text for
non-English files when the rest of the page is translated).

```json
{
  "files": {
    "versions": {
      "section_label": "Versions",
      "current": "Current",
      "superseded": "Superseded",
      "no_history": "No history",
      "load_failed": "Versions unavailable",
      "make_current": "Make current",
      "make_current_title": "Promote this version to current",
      "dropdown_aria": "File version history",
      "restored_title": "Restored to V{{n}}",
      "restore_failed": "Could not restore version"
    }
  }
}
```

## 3. Backend wiring (no UI changes needed)

The upload pipeline in the documents / photos / sheets / BIM /
DWG / takeoff / report / markup services should call
`FileVersionService.register_new_version(...)` after a successful
upload. Wire this in a follow-up — the version table is fully
functional from the API right now and the dropdown will populate
itself once any module starts writing version rows.

The service is importable directly:

```python
from app.modules.file_versions.service import FileVersionService
from app.modules.file_versions.schemas import FileVersionCreate

svc = FileVersionService(session)
await svc.register_new_version(
    FileVersionCreate(
        project_id=project_id,
        file_kind="document",
        file_id=str(doc.id),
        canonical_name=doc.name,
        notes=request_note,
        file_size=doc.file_size,
        checksum=sha256_hex,
    ),
    uploaded_by_id=user_uuid,
)
```
