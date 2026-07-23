// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Give the client a project portal".
//
// Open a controlled window onto the job for the client. Pick what they see,
// expose the agreed payment position and publish a progress pack they can read
// without another meeting.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "give-the-client-a-project-portal",
  order: 336,
  category: "commercial",
  companyTypes: ["developer-client", "owner-operator", "general-contractor"],
  icon: "Users",
  titleKey: "cases.give_the_client_a_project_portal.title",
  titleDefault: "Give the client a project portal",
  descKey: "cases.give_the_client_a_project_portal.desc",
  descDefault:
    "Open a controlled window onto the job for the client: choose what they see, show them the agreed payment position, and publish a progress pack they can read without another meeting.",
  estMinutes: 8,
  steps: [
    {
      id: "portal",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.give_the_client_a_project_portal.step.portal.in.progress",
          label: "Progress & valuations",
        },
        {
          labelKey:
            "cases.give_the_client_a_project_portal.step.portal.in.documents",
          label: "Shared document set",
        },
        {
          labelKey:
            "cases.give_the_client_a_project_portal.step.portal.in.visibility",
          label: "Visibility settings",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.give_the_client_a_project_portal.step.portal.out.view",
          label: "Read-only client view",
        },
        {
          labelKey:
            "cases.give_the_client_a_project_portal.step.portal.out.access",
          label: "Client portal access",
        },
      ],
      titleKey: "cases.give_the_client_a_project_portal.step.portal.title",
      titleDefault: "Choose what the client sees",
      whatKey: "cases.give_the_client_a_project_portal.step.portal.what",
      whatDefault:
        "In the portal, switch on the panels the client should have, progress, valuations and the shared document set, and leave off anything internal such as your cost or margin. Set it once and they get a read-only view that keeps itself up to date.",
      whyKey: "cases.give_the_client_a_project_portal.step.portal.why",
      whyDefault:
        "A client with their own live view stops phoning round for updates and stops guessing. Controlling exactly what is shared keeps your cost and internal correspondence private while the job still looks open.",
      moduleLabel: "Portal",
      moduleLabelKey: "nav.portal",
      to: "/projects/:projectId/portal",
    },
    {
      id: "payment",
      icon: "Banknote",
      inputs: [
        {
          labelKey:
            "cases.give_the_client_a_project_portal.step.payment.in.certified",
          label: "Certified payment position",
        },
        {
          labelKey:
            "cases.give_the_client_a_project_portal.step.payment.in.application",
          label: "Payment application",
        },
        {
          labelKey:
            "cases.give_the_client_a_project_portal.step.payment.in.portal",
          label: "Client portal",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.give_the_client_a_project_portal.step.payment.out.published",
          label: "Published payment figure",
        },
        {
          labelKey:
            "cases.give_the_client_a_project_portal.step.payment.out.shared",
          label: "Shared approved amount",
        },
      ],
      titleKey: "cases.give_the_client_a_project_portal.step.payment.title",
      titleDefault: "Expose the approved payment position",
      whatKey: "cases.give_the_client_a_project_portal.step.payment.what",
      whatDefault:
        "Publish the certified payment position to the portal, what has been applied for, what is approved and what is due, so the client sees the same figure you do. Only the agreed numbers go out, not draft workings.",
      whyKey: "cases.give_the_client_a_project_portal.step.payment.why",
      whyDefault:
        "Payment arguments usually start from two different spreadsheets. One approved figure both sides can see heads off the dispute and gets the invoice paid on time.",
      moduleLabel: "Finance",
      moduleLabelKey: "nav.finance",
      to: "/projects/:projectId/finance",
    },
    {
      id: "pack",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.give_the_client_a_project_portal.step.pack.in.photos",
          label: "Progress photos",
        },
        {
          labelKey:
            "cases.give_the_client_a_project_portal.step.pack.in.percent",
          label: "Percent complete",
        },
        {
          labelKey:
            "cases.give_the_client_a_project_portal.step.pack.in.summary",
          label: "Period summary",
        },
      ],
      outputs: [
        {
          labelKey: "cases.give_the_client_a_project_portal.step.pack.out.pack",
          label: "Client progress pack",
        },
        {
          labelKey:
            "cases.give_the_client_a_project_portal.step.pack.out.published",
          label: "Published to portal",
        },
      ],
      titleKey: "cases.give_the_client_a_project_portal.step.pack.title",
      titleDefault: "Publish the progress pack",
      whatKey: "cases.give_the_client_a_project_portal.step.pack.what",
      whatDefault:
        "Generate the client progress pack, photos, percent complete and the period summary, and publish it straight to the portal on the same day each month. The client reads it in their own time.",
      whyKey: "cases.give_the_client_a_project_portal.step.pack.why",
      whyDefault:
        "A dated pack the client pulls for themselves is proof the job was reported, on time, every period. It replaces the monthly meeting that never quite covers everything and is never written down.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
