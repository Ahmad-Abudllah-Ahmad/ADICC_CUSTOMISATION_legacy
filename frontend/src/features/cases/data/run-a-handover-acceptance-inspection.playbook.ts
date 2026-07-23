// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run a handover acceptance inspection".
//
// Walk the finished works with the client, record what passes and what does
// not, drive the defects to zero, then issue acceptance. Content strings are
// key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "run-a-handover-acceptance-inspection",
  order: 155,
  category: "handover",
  companyTypes: [
    "general-contractor",
    "project-manager",
    "owner-operator",
    "developer-client",
  ],
  icon: "ClipboardCheck",
  titleKey: "cases.run_a_handover_acceptance_inspection.title",
  titleDefault: "Run a handover acceptance inspection",
  descKey: "cases.run_a_handover_acceptance_inspection.desc",
  descDefault:
    "Walk the finished works with the client, record what passes and what does not against the acceptance criteria, drive the defect list down to zero and issue a clean acceptance.",
  estMinutes: 11,
  steps: [
    {
      id: "inspect",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey:
            "cases.run_a_handover_acceptance_inspection.step.inspect.in.works",
          label: "Finished works",
        },
        {
          labelKey:
            "cases.run_a_handover_acceptance_inspection.step.inspect.in.criteria",
          label: "Acceptance criteria",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_handover_acceptance_inspection.step.inspect.out.record",
          label: "Inspection record",
        },
        {
          labelKey:
            "cases.run_a_handover_acceptance_inspection.step.inspect.out.results",
          label: "Pass/fail results",
        },
      ],
      titleKey: "cases.run_a_handover_acceptance_inspection.step.inspect.title",
      titleDefault: "Walk the acceptance inspection",
      whatKey: "cases.run_a_handover_acceptance_inspection.step.inspect.what",
      whatDefault:
        "Go through the works area by area against the agreed acceptance criteria, marking each item pass or fail with a note and a photo, and record who attended and what was witnessed.",
      whyKey: "cases.run_a_handover_acceptance_inspection.step.inspect.why",
      whyDefault:
        "A structured inspection against written criteria replaces a vague walkaround where each side remembers a different outcome. A shared, evidenced record is what stops the acceptance turning into an argument later.",
      moduleLabel: "Inspections",
      moduleLabelKey: "inspections.title",
      to: "/projects/:projectId/inspections",
    },
    {
      id: "defects",
      icon: "ListChecks",
      inputs: [
        {
          labelKey:
            "cases.run_a_handover_acceptance_inspection.step.defects.in.failed",
          label: "Failed items",
        },
        {
          labelKey:
            "cases.run_a_handover_acceptance_inspection.step.defects.in.trades",
          label: "Responsible trades",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_handover_acceptance_inspection.step.defects.out.punch",
          label: "Punch list entries",
        },
        {
          labelKey:
            "cases.run_a_handover_acceptance_inspection.step.defects.out.zero",
          label: "Defect list at zero",
        },
      ],
      titleKey: "cases.run_a_handover_acceptance_inspection.step.defects.title",
      titleDefault: "Clear the defect list",
      whatKey: "cases.run_a_handover_acceptance_inspection.step.defects.what",
      whatDefault:
        "Turn every failed item into a punch list entry with its location, owner and a due date, hand each to the trade responsible and track the list down to nothing before you call it done.",
      whyKey: "cases.run_a_handover_acceptance_inspection.step.defects.why",
      whyDefault:
        "The defect list is the exact distance between practically complete and truly accepted, and the client feels every open item. Driving it to zero is usually what releases acceptance and the payment tied to it.",
      moduleLabel: "Punch list",
      moduleLabelKey: "nav.punchlist",
      to: "/punchlist",
    },
    {
      id: "accept",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.run_a_handover_acceptance_inspection.step.accept.in.zero",
          label: "Defect list at zero",
        },
        {
          labelKey:
            "cases.run_a_handover_acceptance_inspection.step.accept.in.record",
          label: "Inspection record",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_handover_acceptance_inspection.step.accept.out.signed",
          label: "Signed acceptance",
        },
        {
          labelKey:
            "cases.run_a_handover_acceptance_inspection.step.accept.out.defects",
          label: "Defects period started",
        },
      ],
      titleKey: "cases.run_a_handover_acceptance_inspection.step.accept.title",
      titleDefault: "Issue acceptance",
      whatKey: "cases.run_a_handover_acceptance_inspection.step.accept.what",
      whatDefault:
        "Confirm every acceptance item is passed and the punch list is closed, then issue the signed acceptance to the client with the inspection record and photos attached as the evidence behind it.",
      whyKey: "cases.run_a_handover_acceptance_inspection.step.accept.why",
      whyDefault:
        "Acceptance is what starts the defects liability period from an agreed, documented point and shifts care of the works to the client. Issuing it cleanly, with the record behind it, protects you through the warranty years.",
      moduleLabel: "Close-out",
      moduleLabelKey: "nav.closeout",
      to: "/closeout",
    },
  ],
};

export default playbook;
