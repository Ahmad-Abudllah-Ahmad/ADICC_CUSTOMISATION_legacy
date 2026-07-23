// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Set up the asset register for FM".
//
// A handover case for the operator: capture the installed assets with their
// location, type and key data, attach the manuals and warranties, and hand
// over a register maintenance can run from day one. Content strings are key
// plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "set-up-the-asset-register-for-fm",
  order: 270,
  category: "handover",
  companyTypes: ["owner-operator", "developer-client"],
  icon: "Boxes",
  titleKey: "cases.set_up_the_asset_register_for_fm.title",
  titleDefault: "Set up the asset register for FM",
  descKey: "cases.set_up_the_asset_register_for_fm.desc",
  descDefault:
    "Build the asset register the operator will run the building from: capture the installed assets with their location, type and key data, attach the manuals and warranties, and hand it over so maintenance can start from day one.",
  estMinutes: 11,
  steps: [
    {
      id: "capture",
      icon: "Boxes",
      inputs: [
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.capture.in.equipment",
          label: "Installed equipment",
        },
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.capture.in.asbuilt",
          label: "As-built records",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.capture.out.list",
          label: "Tagged asset list",
        },
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.capture.out.tags",
          label: "Asset tags",
        },
      ],
      titleKey: "cases.set_up_the_asset_register_for_fm.step.capture.title",
      titleDefault: "Capture the installed assets",
      whatKey: "cases.set_up_the_asset_register_for_fm.step.capture.what",
      whatDefault:
        "List every maintainable asset that was actually installed, its type, make and model, and give each one a tag so it can be found and referred to without ambiguity.",
      whyKey: "cases.set_up_the_asset_register_for_fm.step.capture.why",
      whyDefault:
        "The register is only useful if it matches the building. An asset that was swapped during construction but never updated in the list leaves the operator maintaining a machine that was never fitted.",
      moduleLabel: "Project files",
      moduleLabelKey: "nav.project_files",
      to: "/projects/:projectId/files",
    },
    {
      id: "locate",
      icon: "MapPin",
      inputs: [
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.locate.in.assets",
          label: "Tagged asset list",
        },
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.locate.in.layout",
          label: "Floor and room layout",
        },
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.locate.in.specs",
          label: "Equipment specifications",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.locate.out.located",
          label: "Located assets",
        },
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.locate.out.data",
          label: "Key asset data",
        },
      ],
      titleKey: "cases.set_up_the_asset_register_for_fm.step.locate.title",
      titleDefault: "Record location and key data",
      whatKey: "cases.set_up_the_asset_register_for_fm.step.locate.what",
      whatDefault:
        "For each asset record where it sits, floor, room and the system it serves, along with the key data a maintainer needs such as rating, capacity and service intervals.",
      whyKey: "cases.set_up_the_asset_register_for_fm.step.locate.why",
      whyDefault:
        "When a unit fails, the first question is always where it is and what serves it. A register that answers that in one line saves the maintenance team hours of hunting through plant rooms and ceilings.",
      moduleLabel: "Quality",
      moduleLabelKey: "nav.qms",
      to: "/projects/:projectId/qms",
    },
    {
      id: "attach",
      icon: "Paperclip",
      inputs: [
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.attach.in.register",
          label: "Located asset register",
        },
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.attach.in.manuals",
          label: "Operation manuals",
        },
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.attach.in.warranties",
          label: "Warranties and spares",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.attach.out.linked",
          label: "Documents linked",
        },
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.attach.out.register",
          label: "Complete asset register",
        },
      ],
      titleKey: "cases.set_up_the_asset_register_for_fm.step.attach.title",
      titleDefault: "Attach manuals and warranties",
      whatKey: "cases.set_up_the_asset_register_for_fm.step.attach.what",
      whatDefault:
        "Link each asset to its operation manual, spare parts list and warranty, so opening the asset gives the maintainer everything they need without a separate search.",
      whyKey: "cases.set_up_the_asset_register_for_fm.step.attach.why",
      whyDefault:
        "A register with the documents attached turns a name in a list into a working record. Without the manual and the warranty in reach, the maintainer is back to guessing and the warranty is easy to miss.",
      moduleLabel: "Close-out",
      moduleLabelKey: "nav.closeout",
      to: "/closeout",
    },
    {
      id: "handover",
      icon: "FileText",
      inputs: [
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.handover.in.register",
          label: "Complete asset register",
        },
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.handover.in.team",
          label: "Maintenance team",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.handover.out.issued",
          label: "Issued register",
        },
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.handover.out.summary",
          label: "Coverage summary",
        },
        {
          labelKey:
            "cases.set_up_the_asset_register_for_fm.step.handover.out.ppm",
          label: "Day-one maintenance ready",
        },
      ],
      titleKey: "cases.set_up_the_asset_register_for_fm.step.handover.title",
      titleDefault: "Hand over so maintenance can start",
      whatKey: "cases.set_up_the_asset_register_for_fm.step.handover.what",
      whatDefault:
        "Issue the completed register to the maintenance team as the record they will run from, and produce a summary of what it covers so day-one planned maintenance can be set up straight away.",
      whyKey: "cases.set_up_the_asset_register_for_fm.step.handover.why",
      whyDefault:
        "The point of the register is a running building, not a filed document. Handing it over ready to use is what lets the operator start planned maintenance from day one instead of rebuilding the list themselves.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
