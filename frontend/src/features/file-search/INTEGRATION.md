# File Search (W3) — Integration Instructions

This feature ships independently from the shared file-manager UI. Splice the
following snippets into the shared files to wire it in. **Do not modify the
shared files yourself** — these are the exact splices a maintainer should
make.

## 1. `FileActionsBar.tsx` — Add the mode toggle

**File:** `frontend/src/features/file-manager/components/FileActionsBar.tsx`

### 1a. Add the import (near the existing imports)

```tsx
import { SearchModeToggle } from '@/features/file-search/SearchModeToggle';
import type { SearchMode } from '@/features/file-search/types';
```

### 1b. Extend the props interface

```tsx
interface FileActionsBarProps {
  // ...existing props
  searchMode?: SearchMode;
  onSearchModeChange?: (mode: SearchMode) => void;
}
```

### 1c. Splice the toggle inside the search input wrapper

Find the existing `<div className="relative flex-1 min-w-[200px] max-w-md">`
block that wraps the `<input type="search">` (around line 89). **Immediately
after that wrapper**, splice:

```tsx
{onSearchModeChange && (
  <SearchModeToggle
    mode={searchMode ?? 'filename'}
    onChange={onSearchModeChange}
  />
)}
```

The toggle defaults to **Filename** so the existing search behaviour is
preserved unless the parent opts in.

## 2. `FileManagerPage.tsx` — Drive the toggle + results pane

**File:** `frontend/src/features/file-manager/FileManagerPage.tsx`

### 2a. Add the imports

```tsx
import { useContentSearch } from '@/features/file-search/hooks';
import { SearchResults } from '@/features/file-search/SearchResults';
import type { SearchMode } from '@/features/file-search/types';
```

### 2b. Add state next to the existing query state

```tsx
const [searchMode, setSearchMode] = useState<SearchMode>('filename');
```

### 2c. Wire the hook (only fires when mode === 'content')

```tsx
const contentSearch = useContentSearch(
  projectId,
  searchMode === 'content' ? query : '',
  undefined,
  searchMode,
);
```

### 2d. Pass props into the actions bar

```tsx
<FileActionsBar
  /* ...existing props */
  searchMode={searchMode}
  onSearchModeChange={setSearchMode}
/>
```

### 2e. When `searchMode === 'content' && query.trim()`, render `<SearchResults>`
instead of (or above) the file grid:

```tsx
{searchMode === 'content' && query.trim() ? (
  <SearchResults
    hits={contentSearch.data?.hits ?? []}
    query={query}
    isLoading={contentSearch.isLoading}
    onOpen={(hit) => navigate(`/projects/${projectId}/files/${hit.kind}/${hit.file_id}`)}
  />
) : (
  /* the existing <FileGrid> / <FileList> render */
)}
```

## 3. (Optional) Index files on upload

**File:** wherever the file-manager's upload mutation succeeds (likely
`frontend/src/features/file-manager/components/UploadDialog.tsx`).

### 3a. Add the import

```tsx
import { useIndexFile } from '@/features/file-search/hooks';
```

### 3b. Inside the component, after the upload mutation:

```tsx
const indexFileMutation = useIndexFile();
```

### 3c. In the upload `onSuccess` callback, fire-and-forget the indexer:

```tsx
indexFileMutation.mutate({
  project_id: projectId,
  file_kind: 'document',
  file_id: uploaded.id,
});
```

OCR runs synchronously in the backend service call; the toast / mutation
result is non-blocking because the user already sees the upload success
toast.

## 4. (Optional) Drop from index on delete

**File:** `frontend/src/features/file-manager/components/BulkActionsBar.tsx`

### 4a. Add the import

```tsx
import { removeFromIndex } from '@/features/file-search/api';
```

### 4b. After a successful delete, fire-and-forget:

```ts
await Promise.allSettled(
  selectedRows.map((row) =>
    removeFromIndex(projectId, row.id, row.kind).catch(() => {}),
  ),
);
```

## New translation keys

Add to `frontend/src/app/locales/en.ts` (and other locales as you translate):

```ts
'files.search.mode_label': 'Search mode',
'files.search.mode_filename': 'Filename',
'files.search.mode_content': 'Content',
'files.search.empty': 'No matching files yet.',
'files.search.results': 'Search results',
'files.search.pages': '{{count}} pages',
'files.search.score': 'Score {{score}}',
```

## API summary (for backend deploy notes)

| Method | Path | Permission | Purpose |
|--------|------|------------|---------|
| POST | `/api/v1/file-search/index/` | `file_search.index` | Index one file by id |
| GET | `/api/v1/file-search/` | `file_search.read` | Run a search |
| POST | `/api/v1/file-search/reindex/` | `file_search.index` | Re-OCR every file |
| DELETE | `/api/v1/file-search/{file_id}/` | `file_search.index` | Drop one row |

The migration is `backend/alembic/versions/v3061_file_search_tags.py`. Run
`alembic upgrade head` to apply.

## Optional dependencies

The OCR pipeline is **graceful-degradation by design**:

* `PyMuPDF` (a.k.a. `fitz`) — embedded PDF text extraction. If missing,
  PDFs fall through to OCR.
* `pytesseract` + `Pillow` — Tesseract OCR for scanned PDFs and image
  files. If missing, image content is not searchable but the file is
  still findable by filename.

`requirements.txt` is unchanged; existing deployments without these
libraries will see `ocr_engine = 'none'` for indexed files. The endpoint
never crashes.
