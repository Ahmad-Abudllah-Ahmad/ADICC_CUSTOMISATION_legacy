# File Approvals + Stamps (W8) — integration into /files

The file-manager team owns the shared components. **Do not edit them
directly**; this document gives the exact splice points + JSX
fragments to merge.

## 1. "Submit for approval" + drawer toggle in `FilePreviewPane.tsx`

Add a new action in the preview pane that opens
`SubmitForApprovalModal`. When the file has an in-flight workflow,
expose an "Approval status" button that opens `ApprovalDrawer`.

Imports:

```tsx
import { CheckCircle2, ClipboardCheck } from 'lucide-react';
import { ApprovalDrawer } from '@/features/file-approvals/ApprovalDrawer';
import { SubmitForApprovalModal } from '@/features/file-approvals/SubmitForApprovalModal';
import { useApprovals } from '@/features/file-approvals/hooks';
```

State + JSX:

```tsx
const [submitOpen, setSubmitOpen] = useState(false);
const [drawerOpen, setDrawerOpen] = useState(false);

// Surface the active workflow (if any) for the current file. The
// hooks layer scopes by project; we filter by file here so the
// preview pane never lists unrelated workflows.
const { data: projectWorkflows = [] } = useApprovals(row?.project_id);
const activeWorkflow = row
  ? projectWorkflows.find(
      (w) =>
        w.file_kind === row.kind &&
        w.file_id === row.id &&
        w.status === 'in_review',
    )
  : undefined;

// Add a "Submit for approval" button in the actions list:
<button
  type="button"
  onClick={() => setSubmitOpen(true)}
  className="flex items-center gap-2 px-3 py-2 text-sm rounded-md hover:bg-surface-secondary"
>
  <ClipboardCheck size={14} />
  {t('files.approvals.submit_action', { defaultValue: 'Submit for approval' })}
</button>

// Show the drawer toggle when a workflow exists:
{activeWorkflow && (
  <button
    type="button"
    onClick={() => setDrawerOpen(true)}
    className="flex items-center gap-2 px-3 py-2 text-sm rounded-md hover:bg-surface-secondary"
  >
    <CheckCircle2 size={14} />
    {t('files.approvals.view_status', {
      defaultValue: 'Approval status',
    })}
  </button>
)}

// Modals at the end of the preview-pane fragment:
{row && (
  <SubmitForApprovalModal
    open={submitOpen}
    onClose={() => setSubmitOpen(false)}
    projectId={row.project_id}
    fileKind={row.kind}
    fileId={row.id}
    fileLabel={row.name}
  />
)}
<ApprovalDrawer
  open={drawerOpen}
  workflowId={activeWorkflow?.id ?? null}
  onClose={() => setDrawerOpen(false)}
/>
```

## 2. Optional: stamped-artifact download badge

If you want to surface a "Download stamped" pill in the preview pane
when a workflow has finalised and a stamp is burned, add to the file
header area:

```tsx
{activeWorkflow?.stamped_artifact_path && (
  <Badge variant="success" size="sm">
    {t('files.approvals.stamped', { defaultValue: 'Stamped' })}
  </Badge>
)}
```

The drawer's own footer already exposes a "Download stamped" button
for any workflow that has `stamped_artifact_path` set.

## 3. New translation keys

All keys live under `files.approvals.*`:

- `files.approvals.submit_action`
- `files.approvals.view_status`
- `files.approvals.modal_title`
- `files.approvals.stamp_section`, `…steps_section`, `…notes_section`
- `files.approvals.steps_help`, `…no_steps`, `…add_step`
- `files.approvals.pick_approver`, `…role_label`
- `files.approvals.submit`, `…submit_failed`, `…submitted`
- `files.approvals.drawer_title`
- `files.approvals.submitter_notes`
- `files.approvals.status.{in_review,approved,rejected,withdrawn}`
- `files.approvals.decision.{pending,approved,rejected,delegated}`
- `files.approvals.approver_step`
- `files.approvals.your_turn`, `…note_placeholder`, `…decide`
- `files.approvals.approve`, `…reject`
- `files.approvals.step_approved`, `…step_rejected`, `…decision_failed`
- `files.approvals.withdraw`, `…withdrew`, `…withdraw_failed`
- `files.approvals.download_stamped`, `…download_failed`
- `files.approvals.stamp_picker`, `…no_stamp`, `…create_custom`
- `files.approvals.stamp_name`, `…stamp_text`, `…stamp_color`,
  `…stamp_svg`, `…stamp_svg_hint`, `…stamp_preview`
- `files.approvals.stamp_created`, `…stamp_create_failed`,
  `…stamp_name_required`
- `files.approvals.editor_title`
- `files.approvals.stamped`

Every key ships with a `defaultValue` so untranslated locales degrade
gracefully to English.

## 4. RBAC permissions registered by the module

- `file_approvals.read`          — viewer+
- `file_approvals.submit`        — editor+
- `file_approvals.decide`        — editor+
- `file_approvals.manage_stamps` — manager+

The decide endpoint additionally checks that the calling user is the
approver assigned to the step (or holds the admin role).

## 5. API surface (mounted by the module loader)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/file-approvals/?project_id={uuid}&status=…` | List workflows |
| POST | `/api/v1/file-approvals/` | Submit for approval |
| GET | `/api/v1/file-approvals/{id}/` | Workflow detail |
| POST | `/api/v1/file-approvals/{id}/steps/{step_id}/decide/` | Record decision |
| POST | `/api/v1/file-approvals/{id}/withdraw/` | Withdraw |
| GET | `/api/v1/file-approvals/{id}/stamped/` | Stamped bytes |
| GET | `/api/v1/file-approvals/stamp-templates/` | List templates |
| POST | `/api/v1/file-approvals/stamp-templates/` | Create custom template |

## 6. Default stamp templates

The alembic migration seeds four global templates with
`project_id=NULL`:

- **For Construction** (green `#16a34a`)
- **Approved** (blue `#2563eb`)
- **Revise & Resubmit** (yellow `#ca8a04`)
- **Rejected** (red `#dc2626`)

Project-scoped templates override globals by name. `StampPicker` will
display the project's set first when a `projectId` is passed.

## 7. Stamp burning behaviour

When the final pending step is approved:

1. The service tries to read the source file bytes via the storage
   backend at a small set of well-known keys.
2. If the file is a PDF and `pypdf` + `reportlab` are importable, a
   stamp overlay is composed via reportlab and merged onto every page,
   producing a sibling `{file_id}__stamped.pdf` blob.
3. Otherwise (non-PDF, or `pypdf` missing) a `{file_id}__stamped.json`
   sidecar is written containing the workflow id, stamp template, the
   expanded SVG (with `{{text}}`, `{{date}}`, `{{approver}}` resolved)
   and the approver label.

In both cases, the storage key is persisted on
`oe_file_approval_workflow.stamped_artifact_path` and exposed via the
`/{id}/stamped/` endpoint. The original source file is never modified.
