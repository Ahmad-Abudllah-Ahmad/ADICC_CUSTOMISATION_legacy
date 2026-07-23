// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Manage the drawing register and transmittals".
//
// A document control case: log every drawing and its current revision, issue
// drawings by formal transmittal, track who holds the latest, and make sure
// superseded revisions cannot be worked to. Content strings are key plus
// inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "manage-the-drawing-register-and-transmittals",
  order: 271,
  category: "handover",
  companyTypes: ["general-contractor", "bim-consultant"],
  icon: "FileStack",
  titleKey: "cases.manage_the_drawing_register_and_transmittals.title",
  titleDefault: "Manage the drawing register and transmittals",
  descKey: "cases.manage_the_drawing_register_and_transmittals.desc",
  descDefault:
    "Keep the drawing register under control: log every drawing and its current revision, issue drawings by formal transmittal, track who holds the latest, and make sure superseded revisions cannot be worked to.",
  estMinutes: 10,
  steps: [
    {
      id: "register",
      icon: "FileStack",
      inputs: [
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.register.in.drawings",
          label: "Incoming drawings",
        },
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.register.in.revisions",
          label: "New revisions",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.register.out.register",
          label: "Drawing register",
        },
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.register.out.current",
          label: "Current revision status",
        },
      ],
      titleKey:
        "cases.manage_the_drawing_register_and_transmittals.step.register.title",
      titleDefault: "Log every drawing and revision",
      whatKey:
        "cases.manage_the_drawing_register_and_transmittals.step.register.what",
      whatDefault:
        "Keep one register that lists every drawing by number, title and current revision, and update it the moment a new revision lands so the register always shows the true latest state.",
      whyKey:
        "cases.manage_the_drawing_register_and_transmittals.step.register.why",
      whyDefault:
        "The register is the single source of truth for what the current drawing is. When it lags behind, two people end up certain they have the latest and only one of them is right.",
      moduleLabel: "Project files",
      moduleLabelKey: "nav.project_files",
      to: "/projects/:projectId/files",
    },
    {
      id: "transmit",
      icon: "Send",
      inputs: [
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.transmit.in.register",
          label: "Drawing register",
        },
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.transmit.in.recipients",
          label: "Recipient list",
        },
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.transmit.in.purpose",
          label: "Issue purpose",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.transmit.out.transmittal",
          label: "Numbered transmittal",
        },
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.transmit.out.ack",
          label: "Receipt acknowledgement",
        },
      ],
      titleKey:
        "cases.manage_the_drawing_register_and_transmittals.step.transmit.title",
      titleDefault: "Issue drawings by formal transmittal",
      whatKey:
        "cases.manage_the_drawing_register_and_transmittals.step.transmit.what",
      whatDefault:
        "Send each drawing out on a numbered transmittal that records what was issued, to whom, at what revision and for what purpose, and keep the acknowledgement of receipt.",
      whyKey:
        "cases.manage_the_drawing_register_and_transmittals.step.transmit.why",
      whyDefault:
        "A formal transmittal is the proof that the right revision reached the right party on a given date. If a trade builds to an old drawing, the transmittal record settles who was issued what and when.",
      moduleLabel: "Correspondence",
      moduleLabelKey: "nav.correspondence",
      to: "/projects/:projectId/correspondence",
    },
    {
      id: "track",
      icon: "Users",
      inputs: [
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.track.in.transmittals",
          label: "Transmittal records",
        },
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.track.in.register",
          label: "Current revisions",
        },
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.track.in.distribution",
          label: "Distribution list",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.track.out.matrix",
          label: "Distribution matrix",
        },
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.track.out.confirmed",
          label: "Confirmed holders",
        },
      ],
      titleKey:
        "cases.manage_the_drawing_register_and_transmittals.step.track.title",
      titleDefault: "Track who holds the latest",
      whatKey:
        "cases.manage_the_drawing_register_and_transmittals.step.track.what",
      whatDefault:
        "Keep a live view of which party is on which revision of each drawing, and when a new revision issues, confirm it reached everyone who was working to the one it replaces.",
      whyKey:
        "cases.manage_the_drawing_register_and_transmittals.step.track.why",
      whyDefault:
        "Issuing a revision is only half the job, the other half is knowing it landed. Tracking distribution against the model and the register is what stops a subcontractor quietly building to a superseded sheet.",
      moduleLabel: "3D model",
      moduleLabelKey: "nav.bim",
      to: "/projects/:projectId/bim",
    },
    {
      id: "supersede",
      icon: "FileText",
      inputs: [
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.supersede.in.old",
          label: "Old revisions",
        },
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.supersede.in.register",
          label: "Drawing register",
        },
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.supersede.in.current",
          label: "Live revisions",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.supersede.out.retired",
          label: "Retired revisions",
        },
        {
          labelKey:
            "cases.manage_the_drawing_register_and_transmittals.step.supersede.out.report",
          label: "Register status report",
        },
      ],
      titleKey:
        "cases.manage_the_drawing_register_and_transmittals.step.supersede.title",
      titleDefault: "Retire superseded revisions",
      whatKey:
        "cases.manage_the_drawing_register_and_transmittals.step.supersede.what",
      whatDefault:
        "Mark old revisions as superseded so they are clearly out of use, and report the register state so anyone can see at a glance which revision is live and which is dead.",
      whyKey:
        "cases.manage_the_drawing_register_and_transmittals.step.supersede.why",
      whyDefault:
        "A superseded drawing that still looks current is one of the most common causes of rework on site. Clearly retiring it, and reporting the live state, is what makes sure work only ever follows the right revision.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
