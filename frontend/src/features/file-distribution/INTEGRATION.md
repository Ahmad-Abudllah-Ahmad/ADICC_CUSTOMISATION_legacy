# Integrating file-distribution into the file manager (Wave W10)

This module ships two sub-features that bolt onto the existing
`file-manager` feature without touching its locked files:

1. **Cross-project file search** (`/files/search`)
2. **Distribution lists** + per-folder **subscriptions**

## 1. Route the GlobalSearchPage

**File**: wherever your app's router is wired (commonly
`frontend/src/app/router.tsx` or `frontend/src/AppRoutes.tsx`).

Add the route:

```tsx
import { GlobalSearchPage } from '@/features/file-distribution';

// inside your <Routes>:
<Route path="/files/search" element={<GlobalSearchPage />} />
```

## 2. Add a "Search across projects" entry on FileManagerPage

**File**: `frontend/src/features/file-manager/FileManagerPage.tsx`

`FileManagerPage` is documented as not-to-be-modified, so do this in
the page **header / toolbar** that *wraps* it (commonly the layout
shell) **or** as a small splice next to the existing search input:

```tsx
import { Link } from 'react-router-dom';
import { Search } from 'lucide-react';

// inside the header:
<Link
  to="/files/search"
  className="inline-flex items-center gap-1 text-sm text-content-secondary hover:text-content-primary"
>
  <Search className="h-4 w-4" />
  Search across projects
</Link>
```

If a header splice is unacceptable, mount the link in the app's
global navigation (sidebar or top bar) — the route works the same
way regardless of where the entry point is.

## 3. Add SubscribeFolderButton to the breadcrumb area

**File**: `frontend/src/features/file-manager/FileManagerPage.tsx`

The breadcrumb / path-bar above the file grid is the natural place
for "subscribe to this kind". The splice imports the button and
renders it next to the kind label:

```tsx
import { SubscribeFolderButton } from '@/features/file-distribution';
import { useAuthStore } from '@/stores/useAuthStore';

// inside the breadcrumb row:
const userEmail = useAuthStore((s) => s.userEmail) ?? '';

{projectId && filters.category && userEmail && (
  <SubscribeFolderButton
    projectId={projectId}
    kind={filters.category}
    subscriberEmail={userEmail}
  />
)}
```

The button auto-detects whether the current user already has a
matching subscription and toggles accordingly. It is a no-op when
the user has not narrowed the file list to a single kind.

If your auth store exposes the user's email under a different key
(e.g. `useAuthStore((s) => s.user?.email)`), substitute that lookup —
the only contract the button needs is a string email.

## 4. Add an entry point for DistributionListModal

The modal manages reusable recipient groups; it is not bound to any
specific screen. Common entry points:

* A "Distribution lists" button on the project sidebar.
* A submenu under the existing share/email dialogs in
  `FileActionsBar.tsx` (avoid editing the file directly; expose a
  context-menu hook elsewhere if needed).

Example wiring on any page:

```tsx
import { useState } from 'react';
import { DistributionListModal } from '@/features/file-distribution';

const [modalOpen, setModalOpen] = useState(false);

<Button onClick={() => setModalOpen(true)}>
  Manage distribution lists
</Button>
<DistributionListModal
  open={modalOpen}
  onClose={() => setModalOpen(false)}
  projectId={projectId}
/>
```

## 5. New translation keys

All strings expose `defaultValue` fallbacks so the UI is usable
without translation. To localise:

### Cross-project search (`files.global_search.*`)

| Key                                              | English fallback                                                                 |
| ------------------------------------------------ | -------------------------------------------------------------------------------- |
| `files.global_search.title`                      | Search across all projects                                                       |
| `files.global_search.subtitle`                   | Find a document, sheet or photo by name across every project you can access.     |
| `files.global_search.placeholder`                | e.g. foundation plan, RFI-014, IFC-arch                                          |
| `files.global_search.search_button`              | Search                                                                           |
| `files.global_search.kind_filter_label`          | Kinds                                                                            |
| `files.global_search.metadata_only_notice`       | Searching file names only — content-text index is not installed on this build.   |
| `files.global_search.empty_state`                | Type a search above to begin.                                                    |
| `files.global_search.no_results`                 | No files matched your search.                                                    |
| `files.global_search.unnamed`                    | (unnamed)                                                                        |

### Distribution lists (`files.distribution.*`)

| Key                                          | English fallback                              |
| -------------------------------------------- | --------------------------------------------- |
| `files.distribution.modal_overview_title`    | Distribution lists                            |
| `files.distribution.modal_edit_title`        | {{name}}                                      |
| `files.distribution.new_list`                | New list                                      |
| `files.distribution.empty`                   | No lists yet — create one.                    |
| `files.distribution.count`                   | {{count}} list(s)                             |
| `files.distribution.name_placeholder`        | List name                                     |
| `files.distribution.rename_list_prompt`      | New name                                      |
| `files.distribution.delete_list_confirm`     | Delete list "{{name}}"?                       |
| `files.distribution.members_count`           | {{count}} member(s)                           |
| `files.distribution.shared_label`            | shared                                        |
| `files.distribution.back`                    | Back to lists                                 |
| `files.distribution.member_email`            | Email                                         |
| `files.distribution.member_role`             | Role                                          |
| `files.distribution.add_member`              | Add                                           |
| `files.distribution.no_members`              | No members yet — add one above.               |
| `files.distribution.remove_member`           | Remove member                                 |
| `files.distribution.subscribe`               | Subscribe                                     |
| `files.distribution.subscribed`              | Subscribed                                    |
| `files.distribution.error_name_required`     | Name is required                              |
| `files.distribution.error_email_required`    | Email is required                             |

## Public surface

```ts
import {
  GlobalSearchPage,
  SearchResultCard,
  DistributionListModal,
  SubscribeFolderButton,
  useGlobalFileSearch,
  useDistributionLists,
  useCreateDistributionList,
  useUpdateDistributionList,
  useDeleteDistributionList,
  useAddDistributionMember,
  useRemoveDistributionMember,
  useSubscriptions,
  useCreateSubscription,
  useDeleteSubscription,
  type SearchHit,
  type DistributionList,
  type Subscription,
} from '@/features/file-distribution';
```

## Soft-dependency on `oe_file_search`

The backend search endpoint augments canonical-name matches with
content-text snippets when the optional `oe_file_search` module is
installed. The frontend surfaces this transparently:

* `SearchResponse.used_content_index === false` → only file names
  were searched. The GlobalSearchPage shows a "metadata-only" notice
  so users know snippets are unavailable.
* `SearchResponse.used_content_index === true` → snippets render
  underneath each result card automatically.

No client-side feature flag is needed — the API is the source of
truth.
