# File References — Integration Notes (W9)

The shared file-manager shell must not be modified directly. The
snippets below are the exact edits needed to surface this feature.

## Imports (top of `FilePreviewPane.tsx`)

```tsx
import { NamingViolationBanner } from '@/features/file-references/NamingViolationBanner';
import { ReferencedInPanel } from '@/features/file-references/ReferencedInPanel';
import { IsoNameBuilder } from '@/features/file-references/IsoNameBuilder';
```

## Slot 1 — Banner at top of the preview pane

Render the banner above the file metadata / preview area so a broken
name greets the user before they see the content. The banner returns
`null` when the active file is compliant, so it can be unconditionally
mounted.

```tsx
{projectId && selectedFile && (
  <NamingViolationBanner
    projectId={projectId}
    fileKind={selectedFile.kind}
    fileId={selectedFile.id}
    className="mb-3"
  />
)}
```

## Slot 2 — "Referenced in" panel (below the comments thread)

```tsx
{projectId && selectedFile && (
  <ReferencedInPanel
    projectId={projectId}
    fileKind={selectedFile.kind}
    fileId={selectedFile.id}
    onChipClick={(ref) => {
      // Route to the host entity. Adjust to your router as needed:
      switch (ref.target_type) {
        case 'rfi':
          navigate(`/rfi/${ref.target_id}`);
          break;
        case 'task':
          navigate(`/tasks/${ref.target_id}`);
          break;
        // ...
        default:
          navigate(`/${ref.target_type}/${ref.target_id}`);
      }
    }}
    className="mt-3"
  />
)}
```

## Slot 3 — IsoNameBuilder inline below the banner

When the banner is open and the user wants to fix the name, the
builder can be rendered conditionally below it:

```tsx
{showIsoBuilder && selectedFile && (
  <IsoNameBuilder
    extension={selectedFile.extension}
    onApply={(newName) => renameFile(selectedFile.id, newName)}
    onCancel={() => setShowIsoBuilder(false)}
    className="mt-3"
  />
)}
```

## Imports (top of `FileActionsBar.tsx`)

```tsx
import { useState } from 'react';
import { LinkToEntityModal } from '@/features/file-references/LinkToEntityModal';
import { Button } from '@/shared/ui/Button';
```

## Slot 4 — "Link to entity" action button

Add a button to the actions bar. The modal renders unconditionally and
gates its own visibility on `open`, so it stays mounted for the
preview's lifetime.

```tsx
const [linkOpen, setLinkOpen] = useState(false);

// ... inside the toolbar render:
{selectedFile && projectId && (
  <>
    <Button
      variant="ghost"
      size="sm"
      onClick={() => setLinkOpen(true)}
      data-testid="file-action-link"
    >
      Link…
    </Button>
    <LinkToEntityModal
      open={linkOpen}
      projectId={projectId}
      fileKind={selectedFile.kind}
      fileId={selectedFile.id}
      onClose={() => setLinkOpen(false)}
    />
  </>
)}
```

## Notes

- `NamingViolationBanner` and `ReferencedInPanel` are both
  cache-aware: they re-use the same `useViolations` /
  `useReferencesForFile` query so the file manager can prefetch the
  data once and every consumer renders in-place.
- All copy lives under `files.naming.*`, `files.link.*`, `files.referenced_in_label`,
  `iso.*` namespaces with English `defaultValue`s — locale files
  do not need updating before ship.
- The IsoNameBuilder talks to `POST /validate-name/`, which is a
  pure-server function with no project-id gate — caching is short
  (mutation rather than query) so the live preview stays snappy.
