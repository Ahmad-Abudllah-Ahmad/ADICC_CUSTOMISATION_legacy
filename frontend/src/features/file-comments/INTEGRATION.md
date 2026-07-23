# File Comments — Integration Notes (W6)

The shared file-manager shell must not be modified directly. The
snippets below are the exact edits needed to surface this feature in
`features/file-manager/components/FilePreviewPane.tsx`.

## Imports (top of `FilePreviewPane.tsx`)

```tsx
import { CommentThread } from '@/features/file-comments/CommentThread';
import { PdfWithComments } from '@/features/file-comments/PdfWithComments';
```

## Render slot 1 — Comments sidebar (below file metadata)

Drop this JSX inside the preview pane, after the existing metadata /
properties block. `currentUserId` comes from the auth store
(`useAuthStore.getState().user?.id`); `canResolve` from the user's
role gate.

```tsx
{selectedFile && projectId && (
  <CommentThread
    projectId={projectId}
    fileKind={selectedFile.kind}
    fileId={selectedFile.id}
    currentUserId={currentUserId}
    canResolve={canResolveComments}
    className="mt-4"
  />
)}
```

## Render slot 2 — PDF preview replacement

For documents whose extension is `.pdf`, swap the current iframe-only
preview for the wrapper that hosts the pin overlay:

```tsx
{selectedFile.extension?.toLowerCase() === 'pdf' && previewUrl ? (
  <PdfWithComments
    pdfUrl={previewUrl}
    projectId={projectId}
    fileKind={selectedFile.kind}
    fileId={selectedFile.id}
    currentPage={1}
    className="h-[640px]"
  />
) : (
  /* keep the existing fallback preview here */
)}
```

`PdfWithComments` keeps the iframe semantics of the original preview;
the overlay is `pointer-events: none` except when `onPlacePin` is set,
so it never blocks scroll/zoom on the underlying PDF.

## Notes

- The `@mention` typeahead in `CommentComposer` is **opt-in** —
  pass a `suggestions` prop from the parent page once a project member
  directory hook exists. Without it the composer behaves like a plain
  textarea.
- `CommentThread` lazily loads on mount via React Query; you can wrap
  it in a `<Suspense>` boundary if you want a skeleton while the
  module chunk hydrates.
- Translations live under the `comments.*` namespace and ship with
  English defaults (`defaultValue`), so the feature works before any
  locale file is updated.
