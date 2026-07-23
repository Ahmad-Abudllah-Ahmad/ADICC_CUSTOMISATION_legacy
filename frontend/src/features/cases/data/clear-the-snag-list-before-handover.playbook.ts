// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Clear the snag list before handover".
//
// Drive the defects to zero before you hand over: work the open snags,
// re-inspect the fixes, and only sign the closeout when the list is clear.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "clear-the-snag-list-before-handover",
  order: 278,
  category: "quality",
  companyTypes: ["general-contractor", "project-manager"],
  stage: "handover",
  icon: "ListChecks",
  titleKey: "cases.clear_the_snag_list_before_handover.title",
  titleDefault: "Clear the snag list before handover",
  descKey: "cases.clear_the_snag_list_before_handover.desc",
  descDefault:
    "Drive the defects to zero before you hand over: work the open snags, re-inspect the fixes, and only sign the closeout when the list is genuinely clear.",
  longDescKey: "cases.clear_the_snag_list_before_handover.longdesc",
  longDescDefault:
    "Handing a client a building with a fat snag list is how a project loses its retention and its goodwill in the same week. This case works the open defects down to zero, re-inspects each fix so a closed snag is a proven one, and gates the closeout on a clean list so you hand over finished work rather than a to-do list.",
  estMinutes: 8,
  steps: [
    {
      id: "snags",
      icon: "ListChecks",
      inputs: [
        {
          labelKey:
            "cases.clear_the_snag_list_before_handover.step.snags.in.list",
          label: "Open snag list",
        },
        {
          labelKey:
            "cases.clear_the_snag_list_before_handover.step.snags.in.trades",
          label: "Responsible trades",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.clear_the_snag_list_before_handover.step.snags.out.assigned",
          label: "Assigned defects",
        },
        {
          labelKey:
            "cases.clear_the_snag_list_before_handover.step.snags.out.dates",
          label: "Target close dates",
        },
      ],
      titleKey: "cases.clear_the_snag_list_before_handover.step.snags.title",
      titleDefault: "Work the open snags down",
      whatKey: "cases.clear_the_snag_list_before_handover.step.snags.what",
      whatDefault:
        "Go through the punch list, make sure every open snag is assigned to the trade that owns it with a date to fix by, and chase the ones blocking handover to the front of the queue.",
      whyKey: "cases.clear_the_snag_list_before_handover.step.snags.why",
      whyDefault:
        "A snag with no owner and no date is a snag that does not get fixed. Assigning and dating each one is what turns a stale list into work that actually closes before the handover date.",
      moduleLabel: "Punch list",
      moduleLabelKey: "nav.punchlist",
      to: "/punchlist",
    },
    {
      id: "verify",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey:
            "cases.clear_the_snag_list_before_handover.step.verify.in.fixes",
          label: "Reported fixes",
        },
        {
          labelKey:
            "cases.clear_the_snag_list_before_handover.step.verify.in.details",
          label: "Snag details",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.clear_the_snag_list_before_handover.step.verify.out.closures",
          label: "Verified closures",
        },
        {
          labelKey:
            "cases.clear_the_snag_list_before_handover.step.verify.out.reopened",
          label: "Reopened defects",
        },
      ],
      titleKey: "cases.clear_the_snag_list_before_handover.step.verify.title",
      titleDefault: "Re-inspect the fixes",
      whatKey: "cases.clear_the_snag_list_before_handover.step.verify.what",
      whatDefault:
        "Inspect each snag the trade says is done, close the ones that genuinely pass and reopen the ones that do not, with a photo either way, so closed means checked.",
      whyKey: "cases.clear_the_snag_list_before_handover.step.verify.why",
      whyDefault:
        "A snag closed on the trade's word alone is the one the client finds on their walk-round. A quick re-inspection is what keeps the list honest and stops handover slipping when the client rejects a half-done fix.",
      moduleLabel: "Inspections",
      moduleLabelKey: "nav.inspections",
      to: "/projects/:projectId/inspections",
    },
    {
      id: "signoff",
      icon: "PackageCheck",
      inputs: [
        {
          labelKey:
            "cases.clear_the_snag_list_before_handover.step.signoff.in.closures",
          label: "Verified closures",
        },
        {
          labelKey:
            "cases.clear_the_snag_list_before_handover.step.signoff.in.checklist",
          label: "Handover checklist",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.clear_the_snag_list_before_handover.step.signoff.out.signoff",
          label: "Closeout sign-off",
        },
        {
          labelKey:
            "cases.clear_the_snag_list_before_handover.step.signoff.out.clearance",
          label: "Handover clearance",
        },
      ],
      titleKey: "cases.clear_the_snag_list_before_handover.step.signoff.title",
      titleDefault: "Sign off on a clean list",
      whatKey: "cases.clear_the_snag_list_before_handover.step.signoff.what",
      whatDefault:
        "With the snags verified clear, complete the closeout checklist and record the sign-off, so handover proceeds on evidence that the defects are actually done, not on a promise to finish later.",
      whyKey: "cases.clear_the_snag_list_before_handover.step.signoff.why",
      whyDefault:
        "Handing over on a promise to close snags later is how a defects list becomes a dispute. Gating closeout on a clean, verified list is what protects your retention and your reputation with the client.",
      moduleLabel: "Close-out",
      moduleLabelKey: "closeout.title",
      to: "/closeout",
    },
  ],
};

export default playbook;
