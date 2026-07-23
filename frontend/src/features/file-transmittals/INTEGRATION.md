# File Transmittals (W7) — integration into /files

The file-manager team owns the shared components. **Do not edit them
directly**; this document gives the exact splice points + JSX
fragments to merge.

## 1. App route for the log page

In `frontend/src/app/App.tsx`, add a lazy import beside the existing
`FileManagerPage` lazy:

```tsx
const TransmittalLogPage = lazy(() =>
  import('@/features/file-transmittals/TransmittalLogPage').then((m) => ({
    default: m.TransmittalLogPage,
  })),
);
```

And register the route inside the same authenticated `<Routes>` block
that hosts `/files` (line ~535):

```tsx
<Route
  path="/files/transmittals"
  element={
    <P title="Transmittals">
      <TransmittalLogPage />
    </P>
  }
/>
```

## 2. "Send transmittal" action in `BulkActionsBar.tsx`

When 1+ files are selected, the bulk-actions bar should expose a new
button that opens `NewTransmittalWizard` pre-populated with the
selection.

Add this import at the top of `BulkActionsBar.tsx`:

```tsx
import { Send } from 'lucide-react';
import { NewTransmittalWizard } from '@/features/file-transmittals/NewTransmittalWizard';
```

State + JSX inside `BulkActionsBar`:

```tsx
const [transmittalOpen, setTransmittalOpen] = useState(false);

const preselected = selectedRows.map((row) => ({
  file_kind: row.kind,
  file_id: row.id,
  canonical_name_snapshot: row.name,
}));

// Inside the action toolbar JSX, beside the existing Delete / Move
// buttons:
<Button
  variant="secondary"
  icon={<Send size={14} />}
  onClick={() => setTransmittalOpen(true)}
  disabled={selectedRows.length === 0}
>
  {t('files.transmittals.send_action', { defaultValue: 'Send transmittal' })}
</Button>

// Wizard mounted at the end of the component tree:
<NewTransmittalWizard
  open={transmittalOpen}
  onClose={() => setTransmittalOpen(false)}
  projectId={projectId}
  preselectedItems={preselected}
/>
```

## 3. "Send transmittal" + "Transmittal log" in `FilePreviewPane.tsx`

In the actions list of the right-rail preview pane, add a single-file
"Send transmittal" action and a "View transmittal log" link.

Imports:

```tsx
import { Send } from 'lucide-react';
import { NewTransmittalWizard } from '@/features/file-transmittals/NewTransmittalWizard';
```

State + JSX:

```tsx
const [transmittalOpen, setTransmittalOpen] = useState(false);

// Beside existing "Email link" / "Share" actions:
<button
  type="button"
  onClick={() => setTransmittalOpen(true)}
  className="flex items-center gap-2 px-3 py-2 text-sm rounded-md hover:bg-surface-secondary"
>
  <Send size={14} />
  {t('files.transmittals.send_action', { defaultValue: 'Send transmittal' })}
</button>

// Modal at the end of the preview-pane fragment:
{row && (
  <NewTransmittalWizard
    open={transmittalOpen}
    onClose={() => setTransmittalOpen(false)}
    projectId={row.project_id}
    preselectedItems={[
      {
        file_kind: row.kind,
        file_id: row.id,
        canonical_name_snapshot: row.name,
      },
    ]}
  />
)}
```

## 4. Sidebar / nav link to the log

`/files/transmittals` is best reached from the file-manager toolbar
header. Add an "Open transmittal log" button in `FileManagerPage.tsx`'s
header area:

```tsx
<Link
  to="/files/transmittals"
  className="text-sm text-content-secondary hover:text-content-primary"
>
  {t('files.transmittals.open_log', { defaultValue: 'Transmittal log' })}
</Link>
```

## 5. New translation keys

All keys live under `files.transmittals.*`:

- `files.transmittals.title`
- `files.transmittals.description`
- `files.transmittals.new`
- `files.transmittals.send_action`
- `files.transmittals.open_log`
- `files.transmittals.subject`, `…subject_placeholder`
- `files.transmittals.reason`
- `files.transmittals.reason.{for_review,for_construction,for_approval,for_information,for_record}`
- `files.transmittals.notes`, `…notes_placeholder`
- `files.transmittals.recipient_email`, `…recipient_name`, `…recipient_role`
- `files.transmittals.no_items`, `…no_recipients`
- `files.transmittals.send`, `…sent_title`
- `files.transmittals.cover_download_failed`, `…send_failed`
- `files.transmittals.status.{draft,sent,acknowledged,rejected}`
- `files.transmittals.filter_status`, `…filter_reason`, `…count`
- `files.transmittals.col_number`, `…col_subject`, `…col_reason`,
  `…col_items`, `…col_recipients`, `…col_sent_at`, `…col_status`
- `files.transmittals.detail_title`
- `files.transmittals.items`, `…ack_timeline`, `…ack_done`, `…ack_pending`
- `files.transmittals.no_items_short`, `…no_recipients_short`
- `files.transmittals.download_cover`
- `files.transmittals.wizard.{title,subtitle,step1,step2,step2_help,step3,step3_help}`
- `files.transmittals.invalid_email`, `…duplicate_recipient`
- `files.transmittals.no_project`, `…empty`

Every key ships with a `defaultValue` so untranslated locales degrade
gracefully to English.

## 6. RBAC permissions registered by the module

- `file_transmittals.read`  — viewer+
- `file_transmittals.write` — editor+
- `file_transmittals.send`  — editor+

The public `/api/v1/file-transmittals/ack/{token}/` endpoint is
unauthenticated by design — it gates on the single-use token minted
when the transmittal is sent.

## 7. API surface (mounted by the module loader)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/file-transmittals/?project_id={uuid}` | Log list |
| POST | `/api/v1/file-transmittals/` | Create draft |
| GET | `/api/v1/file-transmittals/{id}` | Full transmittal |
| POST | `/api/v1/file-transmittals/{id}/send/` | Mint tokens, generate cover |
| POST | `/api/v1/file-transmittals/{id}/items/` | Append item |
| DELETE | `/api/v1/file-transmittals/{id}/items/{iid}/` | Remove item |
| POST | `/api/v1/file-transmittals/{id}/recipients/` | Append recipient |
| POST | `/api/v1/file-transmittals/ack/{token}/` | Public ack |
| GET | `/api/v1/file-transmittals/{id}/cover/` | Cover sheet bytes |
