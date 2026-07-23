// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Build and run an inspection and test plan".
//
// Set out the hold and witness points before the work starts, inspect at each
// one as it is reached, and file the signed records as the quality trail.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "build-and-run-an-itp",
  order: 185,
  category: "quality",
  companyTypes: ["general-contractor", "subcontractor", "project-manager"],
  icon: "ListChecks",
  titleKey: "cases.build_and_run_an_itp.title",
  titleDefault: "Build and run an inspection and test plan",
  descKey: "cases.build_and_run_an_itp.desc",
  descDefault:
    "Agree the hold and witness points for a trade before it starts, inspect at each point as the work reaches it, and file the signed records so the quality is proven, not assumed.",
  estMinutes: 11,
  steps: [
    {
      id: "plan",
      icon: "ClipboardList",
      inputs: [
        {
          labelKey: "cases.build_and_run_an_itp.step.plan.in.spec",
          label: "Specification clauses",
        },
        {
          labelKey: "cases.build_and_run_an_itp.step.plan.in.scope",
          label: "Trade scope",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_and_run_an_itp.step.plan.out.itp",
          label: "Inspection and test plan",
        },
        {
          labelKey: "cases.build_and_run_an_itp.step.plan.out.points",
          label: "Hold and witness points",
        },
      ],
      titleKey: "cases.build_and_run_an_itp.step.plan.title",
      titleDefault: "Build the ITP",
      whatKey: "cases.build_and_run_an_itp.step.plan.what",
      whatDefault:
        "Lay out the inspection and test plan for the trade: each check to be made, the acceptance criteria and specification clause behind it, and whether it is a hold point that stops the work or a witness point the client attends.",
      whyKey: "cases.build_and_run_an_itp.step.plan.why",
      whyDefault:
        "Agreeing the checkpoints before the first pour means everyone knows where the work must stop for sign-off, so nothing critical gets covered up in a rush. It turns quality from a hope into a planned sequence.",
      moduleLabel: "Quality management",
      moduleLabelKey: "nav.qms",
      to: "/projects/:projectId/qms",
    },
    {
      id: "execute",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey: "cases.build_and_run_an_itp.step.execute.in.itp",
          label: "ITP hold points",
        },
        {
          labelKey: "cases.build_and_run_an_itp.step.execute.in.works",
          label: "Work at the point",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_and_run_an_itp.step.execute.out.signed",
          label: "Signed inspections",
        },
        {
          labelKey: "cases.build_and_run_an_itp.step.execute.out.holds",
          label: "Pass or hold decision",
        },
      ],
      titleKey: "cases.build_and_run_an_itp.step.execute.title",
      titleDefault: "Inspect at each point",
      whatKey: "cases.build_and_run_an_itp.step.execute.what",
      whatDefault:
        "As the work reaches each point on the plan, raise the inspection, check it against the criteria, and sign it as passed or fail it and hold the next operation until it is put right. Bring the client in at every witness point.",
      whyKey: "cases.build_and_run_an_itp.step.execute.why",
      whyDefault:
        "A hold point inspected on time stops a defect being buried under the next layer, where fixing it costs ten times as much. Catching it at the point is the cheapest quality you will ever buy.",
      moduleLabel: "Inspections",
      moduleLabelKey: "inspections.title",
      to: "/projects/:projectId/inspections",
    },
    {
      id: "record",
      icon: "FolderOpen",
      inputs: [
        {
          labelKey: "cases.build_and_run_an_itp.step.record.in.records",
          label: "Signed inspection records",
        },
        {
          labelKey: "cases.build_and_run_an_itp.step.record.in.certs",
          label: "Test certificates",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_and_run_an_itp.step.record.out.completed",
          label: "Completed ITP",
        },
        {
          labelKey: "cases.build_and_run_an_itp.step.record.out.trail",
          label: "Quality trail filed",
        },
      ],
      titleKey: "cases.build_and_run_an_itp.step.record.title",
      titleDefault: "File the signed records",
      whatKey: "cases.build_and_run_an_itp.step.record.what",
      whatDefault:
        "Gather the signed inspection records, test certificates and any concession against each ITP line, and file them together so the completed plan reads as one continuous quality trail for the element.",
      whyKey: "cases.build_and_run_an_itp.step.record.why",
      whyDefault:
        "The completed ITP with every point signed is what the client and the certifier accept as proof the work is right. Without it, quality already built is worth nothing you can demonstrate at handover.",
      moduleLabel: "Files",
      moduleLabelKey: "nav.documents",
      to: "/projects/:projectId/files",
    },
  ],
};

export default playbook;
