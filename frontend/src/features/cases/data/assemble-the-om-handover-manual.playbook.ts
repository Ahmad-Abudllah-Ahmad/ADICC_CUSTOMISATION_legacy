// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Assemble the O&M handover manual".
//
// A handover case: collect the as-built drawings, product data, test and
// commissioning certificates and warranties, check the set against the
// required index and issue it to the client at handover. Content strings are
// key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "assemble-the-om-handover-manual",
  order: 269,
  category: "handover",
  companyTypes: ["general-contractor", "project-manager", "owner-operator"],
  icon: "BookOpen",
  titleKey: "cases.assemble_the_om_handover_manual.title",
  titleDefault: "Assemble the O&M handover manual",
  descKey: "cases.assemble_the_om_handover_manual.desc",
  descDefault:
    "Pull together the operation and maintenance manual: collect the as-built drawings, product data, test and commissioning certificates and warranties, check the set is complete against the required index and issue it to the client at handover.",
  estMinutes: 13,
  steps: [
    {
      id: "collect",
      icon: "FolderOpen",
      inputs: [
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.collect.in.asbuilt",
          label: "As-built drawings",
        },
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.collect.in.datasheets",
          label: "Product data sheets",
        },
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.collect.in.systems",
          label: "Installed systems",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.collect.out.collected",
          label: "Collected system files",
        },
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.collect.out.verified",
          label: "Verified as-builts",
        },
      ],
      titleKey: "cases.assemble_the_om_handover_manual.step.collect.title",
      titleDefault: "Collect the as-builts and product data",
      whatKey: "cases.assemble_the_om_handover_manual.step.collect.what",
      whatDefault:
        "Gather the as-built drawings and the product data sheets for what was actually installed, one place per system, and make sure each file reflects the final built state rather than an early design version.",
      whyKey: "cases.assemble_the_om_handover_manual.step.collect.why",
      whyDefault:
        "The operator will run the building from these documents for years. An as-built that still shows the design intent, not what the trades actually fitted, sends a maintenance team to the wrong valve on the wrong floor.",
      moduleLabel: "Project files",
      moduleLabelKey: "nav.project_files",
      to: "/projects/:projectId/files",
    },
    {
      id: "certificates",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.certificates.in.certs",
          label: "Commissioning certificates",
        },
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.certificates.in.warranties",
          label: "Product warranties",
        },
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.certificates.in.signoffs",
          label: "Trade sign-offs",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.certificates.out.linked",
          label: "Linked certificates",
        },
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.certificates.out.warranties",
          label: "Warranty register",
        },
      ],
      titleKey: "cases.assemble_the_om_handover_manual.step.certificates.title",
      titleDefault: "Gather test and commissioning certificates",
      whatKey: "cases.assemble_the_om_handover_manual.step.certificates.what",
      whatDefault:
        "Pull in the test, inspection and commissioning certificates and the warranties for each system, and tie every one back to the equipment and the trade that signed it off.",
      whyKey: "cases.assemble_the_om_handover_manual.step.certificates.why",
      whyDefault:
        "These certificates are the proof that the systems were tested and left working, and the warranties are what the client leans on when something fails. A missing certificate at handover often blocks occupation.",
      moduleLabel: "Quality",
      moduleLabelKey: "nav.qms",
      to: "/projects/:projectId/qms",
    },
    {
      id: "check",
      icon: "ListChecks",
      inputs: [
        {
          labelKey: "cases.assemble_the_om_handover_manual.step.check.in.docs",
          label: "Collected documents",
        },
        {
          labelKey: "cases.assemble_the_om_handover_manual.step.check.in.certs",
          label: "Certificate set",
        },
        {
          labelKey: "cases.assemble_the_om_handover_manual.step.check.in.index",
          label: "Required contents index",
        },
      ],
      outputs: [
        {
          labelKey: "cases.assemble_the_om_handover_manual.step.check.out.gaps",
          label: "Gap list",
        },
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.check.out.checked",
          label: "Checked index",
        },
      ],
      titleKey: "cases.assemble_the_om_handover_manual.step.check.title",
      titleDefault: "Check the set against the required index",
      whatKey: "cases.assemble_the_om_handover_manual.step.check.what",
      whatDefault:
        "Run the assembled manual against the required contents index for the handover, mark off what is present, and chase the trades for the last missing drawings, data sheets and certificates before you close it.",
      whyKey: "cases.assemble_the_om_handover_manual.step.check.why",
      whyDefault:
        "A handover manual is judged complete or not against the agreed index, not against how thick it looks. Finding the gaps yourself, before the client does, is what keeps the acceptance and the final payment on track.",
      moduleLabel: "Close-out",
      moduleLabelKey: "nav.closeout",
      to: "/closeout",
    },
    {
      id: "issue",
      icon: "Send",
      inputs: [
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.issue.in.manual",
          label: "Complete manual",
        },
        {
          labelKey: "cases.assemble_the_om_handover_manual.step.issue.in.date",
          label: "Handover date",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.issue.out.issued",
          label: "Issued manual",
        },
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.issue.out.transmittal",
          label: "Transmittal record",
        },
        {
          labelKey: "cases.assemble_the_om_handover_manual.step.issue.out.ack",
          label: "Client acknowledgement",
        },
      ],
      titleKey: "cases.assemble_the_om_handover_manual.step.issue.title",
      titleDefault: "Issue the manual to the client",
      whatKey: "cases.assemble_the_om_handover_manual.step.issue.what",
      whatDefault:
        "Issue the complete manual to the client by a formal transmittal at handover, record the date and what was in the set, and keep the acknowledgement that they received it.",
      whyKey: "cases.assemble_the_om_handover_manual.step.issue.why",
      whyDefault:
        "Handing over the manual formally, with a dated record of exactly what was included, is what discharges your obligation to provide it. A pile of files with no transmittal behind it is easy to dispute months later.",
      moduleLabel: "Correspondence",
      moduleLabelKey: "nav.correspondence",
      to: "/projects/:projectId/correspondence",
    },
    {
      id: "report",
      icon: "FileText",
      inputs: [
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.report.in.issued",
          label: "Issued manual set",
        },
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.report.in.transmittal",
          label: "Transmittal record",
        },
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.report.in.outstanding",
          label: "Outstanding items",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.report.out.report",
          label: "Handover set report",
        },
        {
          labelKey:
            "cases.assemble_the_om_handover_manual.step.report.out.record",
          label: "Project record entry",
        },
      ],
      titleKey: "cases.assemble_the_om_handover_manual.step.report.title",
      titleDefault: "Report the handover set",
      whatKey: "cases.assemble_the_om_handover_manual.step.report.what",
      whatDefault:
        "Produce a short report that lists what the handover set contained, when it was issued and any items still to follow, and keep it with the project record.",
      whyKey: "cases.assemble_the_om_handover_manual.step.report.why",
      whyDefault:
        "A clear summary of what was handed over, and what was still outstanding on the day, is the evidence you point back to if a document is ever queried. It closes the loop on the whole handover cleanly.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
