// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run reactive FM service after handover".
//
// Handle a fault the way a building operator should: log the reactive request
// against the asset, work it with the warranty and O&M data to hand, and close
// it out with a verification check.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "run-reactive-fm-service-after-handover",
  order: 344,
  category: "handover",
  companyTypes: ["owner-operator", "developer-client"],
  roles: ["site-manager", "project-manager"],
  stage: "operate",
  icon: "HardHat",
  titleKey: "cases.run_reactive_fm_service_after_handover.title",
  titleDefault: "Run reactive FM service after handover",
  descKey: "cases.run_reactive_fm_service_after_handover.desc",
  descDefault:
    "Handle a fault the way a building operator should: log the reactive request against the asset, work it with the warranty and O&M data to hand, and close it out with a verification check.",
  longDescKey: "cases.run_reactive_fm_service_after_handover.longdesc",
  longDescDefault:
    "Reactive maintenance lives or dies on traceability, so this case ties every fault straight to the asset that failed and works it with the warranty and O&M data already on file. Log the request, open the asset to see who pays and how the maker says to fix it, then close the job only after a verified check so closed always means fixed.",
  estMinutes: 8,
  steps: [
    {
      id: "request",
      icon: "ClipboardList",
      inputs: [
        {
          labelKey:
            "cases.run_reactive_fm_service_after_handover.step.request.in.fault",
          label: "Reported fault",
        },
        {
          labelKey:
            "cases.run_reactive_fm_service_after_handover.step.request.in.asset",
          label: "Affected asset",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_reactive_fm_service_after_handover.step.request.out.request",
          label: "Logged service request",
        },
        {
          labelKey:
            "cases.run_reactive_fm_service_after_handover.step.request.out.target",
          label: "Response target set",
        },
      ],
      titleKey:
        "cases.run_reactive_fm_service_after_handover.step.request.title",
      titleDefault: "Log the reactive request",
      whatKey: "cases.run_reactive_fm_service_after_handover.step.request.what",
      whatDefault:
        "Raise the service request against the specific asset that failed, with the fault, the location and the priority, so it is tracked from report to fix instead of sitting in an inbox. Set the response target.",
      whyKey: "cases.run_reactive_fm_service_after_handover.step.request.why",
      whyDefault:
        "A fault that is not logged against the asset is one nobody can trend or prove was fixed. Tying it to the asset from the first call is what later tells you which units keep failing and whether the response target was met.",
      moduleLabel: "Service",
      moduleLabelKey: "nav.service",
      to: "/projects/:projectId/service",
    },
    {
      id: "asset",
      icon: "Boxes",
      inputs: [
        {
          labelKey:
            "cases.run_reactive_fm_service_after_handover.step.asset.in.request",
          label: "Logged service request",
        },
        {
          labelKey:
            "cases.run_reactive_fm_service_after_handover.step.asset.in.record",
          label: "Asset record",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_reactive_fm_service_after_handover.step.asset.out.warranty",
          label: "Warranty status",
        },
        {
          labelKey:
            "cases.run_reactive_fm_service_after_handover.step.asset.out.procedure",
          label: "Repair procedure",
        },
        {
          labelKey:
            "cases.run_reactive_fm_service_after_handover.step.asset.out.part",
          label: "Spare part needed",
        },
      ],
      titleKey: "cases.run_reactive_fm_service_after_handover.step.asset.title",
      titleDefault: "Open the asset and its data",
      whatKey: "cases.run_reactive_fm_service_after_handover.step.asset.what",
      whatDefault:
        "Open the asset record to see its make and model, its location and, crucially, whether it is still in warranty and what the O&M manual says. Pull the spare part or the procedure from there.",
      whyKey: "cases.run_reactive_fm_service_after_handover.step.asset.why",
      whyDefault:
        "Fixing a unit that is still under warranty out of your own pocket is money straight out the door. The asset record is what tells the engineer, before they start, who pays and how the maker says to fix it.",
      moduleLabel: "Assets",
      moduleLabelKey: "nav.assets",
      to: "/assets",
    },
    {
      id: "verify",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey:
            "cases.run_reactive_fm_service_after_handover.step.verify.in.repair",
          label: "Completed repair",
        },
        {
          labelKey:
            "cases.run_reactive_fm_service_after_handover.step.verify.in.request",
          label: "Open service request",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_reactive_fm_service_after_handover.step.verify.out.check",
          label: "Verified fix",
        },
        {
          labelKey:
            "cases.run_reactive_fm_service_after_handover.step.verify.out.closed",
          label: "Closed request",
        },
        {
          labelKey:
            "cases.run_reactive_fm_service_after_handover.step.verify.out.history",
          label: "Maintenance history",
        },
      ],
      titleKey:
        "cases.run_reactive_fm_service_after_handover.step.verify.title",
      titleDefault: "Close out with a verification check",
      whatKey: "cases.run_reactive_fm_service_after_handover.step.verify.what",
      whatDefault:
        "Before you mark the job done, run a short verification inspection that the fault is actually cleared and the asset is back to spec, and capture it with a photo. Only then close the request.",
      whyKey: "cases.run_reactive_fm_service_after_handover.step.verify.why",
      whyDefault:
        "A job closed on trust alone is the one that reopens next week. A quick verified check is what makes closed mean fixed, and gives the operator a clean maintenance history on the asset.",
      moduleLabel: "Inspections",
      moduleLabelKey: "nav.inspections",
      to: "/projects/:projectId/inspections",
    },
  ],
};

export default playbook;
