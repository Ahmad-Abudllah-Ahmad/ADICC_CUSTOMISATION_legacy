// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Hand over and close out".
//
// Finish the job cleanly, in five steps: clear the punch list, confirm every
// inspection passed, close the open non-conformances, assemble the as-built
// documents and issue the signed handover. Each step points at a bespoke
// before -> after process scene (see processScenes.tsx). Content strings are a
// key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "handover-and-closeout",
  order: 70,
  category: "handover",
  companyTypes: ["general-contractor", "project-manager", "owner-operator"],
  icon: "ShieldCheck",
  titleKey: "cases.handover_and_closeout.title",
  titleDefault: "Hand over and close out",
  descKey: "cases.handover_and_closeout.desc",
  descDefault:
    "Finish the job cleanly: work the punch list to zero, confirm every inspection passed and no non-conformance is open, gather the as-built record and issue a signed handover.",
  estMinutes: 14,
  steps: [
    {
      id: "punch",
      icon: "ListChecks",
      scene: "punchlist-to-zero",
      inputs: [
        {
          labelKey: "cases.handover_and_closeout.step.punch.in.works",
          label: "Finished works",
        },
        {
          labelKey: "cases.handover_and_closeout.step.punch.in.snags",
          label: "Open snags",
        },
      ],
      outputs: [
        {
          labelKey: "cases.handover_and_closeout.step.punch.out.zero",
          label: "Punch list at zero",
        },
        {
          labelKey: "cases.handover_and_closeout.step.punch.out.signed",
          label: "Trades signed off",
        },
      ],
      titleKey: "cases.handover_and_closeout.step.punch.title",
      titleDefault: "Clear the punch list",
      whatKey: "cases.handover_and_closeout.step.punch.what",
      whatDefault:
        "Walk the finished works room by room, log every snag with its location and a photo, assign each one to the trade responsible and track the list down to nothing.",
      whyKey: "cases.handover_and_closeout.step.punch.why",
      whyDefault:
        "The punch list is the distance between practically complete and genuinely complete, and the client feels every open item. A short list driven to zero is usually what releases the final certificate and the last payment.",
      moduleLabel: "Punch list",
      moduleLabelKey: "nav.punchlist",
      to: "/punchlist",
    },
    {
      id: "inspections",
      icon: "ClipboardCheck",
      scene: "inspections-all-green",
      inputs: [
        {
          labelKey: "cases.handover_and_closeout.step.inspections.in.checklist",
          label: "Inspection checklist",
        },
        {
          labelKey: "cases.handover_and_closeout.step.inspections.in.points",
          label: "Hold & witness points",
        },
      ],
      outputs: [
        {
          labelKey: "cases.handover_and_closeout.step.inspections.out.green",
          label: "Every check green",
        },
        {
          labelKey: "cases.handover_and_closeout.step.inspections.out.records",
          label: "Signed inspection records",
        },
      ],
      titleKey: "cases.handover_and_closeout.step.inspections.title",
      titleDefault: "Confirm the inspections passed",
      whatKey: "cases.handover_and_closeout.step.inspections.what",
      whatDefault:
        "Go through every required inspection, hold point and witness point for the works and confirm each one carries its sign-off, so the whole checklist reads passed with nothing left pending.",
      whyKey: "cases.handover_and_closeout.step.inspections.why",
      whyDefault:
        "A handover pack is only as honest as the inspections behind it. An unsigned check is an open question the client is entitled to ask, so turning the whole list green is what lets you say the work is genuinely accepted, not just finished.",
      moduleLabel: "Inspections",
      moduleLabelKey: "inspections.title",
      to: "/projects/:projectId/inspections",
    },
    {
      id: "nonconformances",
      icon: "ShieldAlert",
      scene: "nonconformance-closing",
      inputs: [
        {
          labelKey:
            "cases.handover_and_closeout.step.nonconformances.in.register",
          label: "Open NCR register",
        },
        {
          labelKey:
            "cases.handover_and_closeout.step.nonconformances.in.actions",
          label: "Corrective actions",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.handover_and_closeout.step.nonconformances.out.closed",
          label: "Every NCR closed",
        },
        {
          labelKey:
            "cases.handover_and_closeout.step.nonconformances.out.evidence",
          label: "Closure evidence attached",
        },
      ],
      titleKey: "cases.handover_and_closeout.step.nonconformances.title",
      titleDefault: "Close the non-conformances",
      whatKey: "cases.handover_and_closeout.step.nonconformances.what",
      whatDefault:
        "Work through the non-conformance register and drive every open item to closed: confirm the corrective action was done, verify it on site and attach the evidence that shuts each report for good.",
      whyKey: "cases.handover_and_closeout.step.nonconformances.why",
      whyDefault:
        "A non-conformance left open at handover does not disappear, it follows the building into occupation and the defects period as a problem for whoever takes the building on. Closing every one, with the evidence attached, is what makes the handover both complete and defensible.",
      moduleLabel: "Non-conformances",
      to: "/projects/:projectId/inspections",
    },
    {
      id: "documents",
      icon: "FolderOpen",
      scene: "gather-handover-docs",
      inputs: [
        {
          labelKey: "cases.handover_and_closeout.step.documents.in.asbuilt",
          label: "As-built drawings",
        },
        {
          labelKey: "cases.handover_and_closeout.step.documents.in.certs",
          label: "Certificates & warranties",
        },
        {
          labelKey: "cases.handover_and_closeout.step.documents.in.manuals",
          label: "O&M manuals",
        },
      ],
      outputs: [
        {
          labelKey: "cases.handover_and_closeout.step.documents.out.index",
          label: "Indexed handover file",
        },
      ],
      titleKey: "cases.handover_and_closeout.step.documents.title",
      titleDefault: "Assemble the documents",
      whatKey: "cases.handover_and_closeout.step.documents.what",
      whatDefault:
        "Collect the as-built drawings, test certificates, product warranties and operating manuals into the project files, indexed so the operator can find any one of them in one place.",
      whyKey: "cases.handover_and_closeout.step.documents.why",
      whyDefault:
        "The client forgets a smooth pour but remembers a messy handover for years. A complete, well ordered document set is both the last impression you leave and the first thing the facilities team actually opens.",
      moduleLabel: "Files",
      moduleLabelKey: "nav.documents",
      to: "/projects/:projectId/files",
    },
    {
      id: "closeout",
      icon: "ShieldCheck",
      scene: "issue-signed-handover",
      inputs: [
        {
          labelKey: "cases.handover_and_closeout.step.closeout.in.checklist",
          label: "Close-out checklist",
        },
        {
          labelKey: "cases.handover_and_closeout.step.closeout.in.docs",
          label: "Complete document set",
        },
      ],
      outputs: [
        {
          labelKey: "cases.handover_and_closeout.step.closeout.out.signed",
          label: "Signed handover issued",
        },
        {
          labelKey: "cases.handover_and_closeout.step.closeout.out.defects",
          label: "Defects period started",
        },
      ],
      titleKey: "cases.handover_and_closeout.step.closeout.title",
      titleDefault: "Issue the handover",
      whatKey: "cases.handover_and_closeout.step.closeout.what",
      whatDefault:
        "Pull the close-out package together, check that every gate from snags to certificates is met and issue the signed handover to both the client and the operator who takes the building on.",
      whyKey: "cases.handover_and_closeout.step.closeout.why",
      whyDefault:
        "Close-out is what turns a finished building into a discharged contractual obligation rather than an open one. Issuing it cleanly sets the defects liability period running from an agreed, documented starting point.",
      moduleLabel: "Close-out",
      moduleLabelKey: "nav.closeout",
      to: "/closeout",
    },
  ],
};

export default playbook;
