// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Coordinate models and resolve clashes".
//
// Combine the discipline models, run the clash test, then drive the real
// conflicts to closure by raising them where site can act on them. Content
// strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "coordinate-models-and-clashes",
  order: 95,
  category: "bim",
  companyTypes: ["designer", "bim-consultant", "project-manager"],
  icon: "Combine",
  titleKey: "cases.coordinate_models_and_clashes.title",
  titleDefault: "Coordinate models and resolve clashes",
  descKey: "cases.coordinate_models_and_clashes.desc",
  descDefault:
    "Bring the discipline models together on one coordinate base, run the clash test, clear the noise, and push the conflicts that matter to the people who can fix them.",
  estMinutes: 13,
  steps: [
    {
      id: "federate",
      icon: "Layers",
      inputs: [
        {
          labelKey: "cases.coordinate_models_and_clashes.step.federate.in.arch",
          label: "Architectural model",
        },
        {
          labelKey:
            "cases.coordinate_models_and_clashes.step.federate.in.struct",
          label: "Structural model",
        },
        {
          labelKey: "cases.coordinate_models_and_clashes.step.federate.in.mep",
          label: "MEP model",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.coordinate_models_and_clashes.step.federate.out.federation",
          label: "Federated model",
        },
        {
          labelKey:
            "cases.coordinate_models_and_clashes.step.federate.out.origin",
          label: "Aligned coordinate base",
        },
      ],
      titleKey: "cases.coordinate_models_and_clashes.step.federate.title",
      titleDefault: "Federate the models",
      whatKey: "cases.coordinate_models_and_clashes.step.federate.what",
      whatDefault:
        "Load the architectural, structural and MEP models into a single federation and confirm every one lands on the same project origin, the same shared grid and the same level naming.",
      whyKey: "cases.coordinate_models_and_clashes.step.federate.why",
      whyDefault:
        "If one model sits a metre off the others, the clash engine reports the whole building colliding with itself. Getting the coordinate base right is the quiet work that makes everything after it meaningful.",
      moduleLabel: "Federations",
      moduleLabelKey: "nav.federations",
      to: "/bim/federations",
    },
    {
      id: "clash",
      icon: "Crosshair",
      inputs: [
        {
          labelKey:
            "cases.coordinate_models_and_clashes.step.clash.in.federation",
          label: "Federated model",
        },
        {
          labelKey: "cases.coordinate_models_and_clashes.step.clash.in.rules",
          label: "Clash test rules",
        },
      ],
      outputs: [
        {
          labelKey: "cases.coordinate_models_and_clashes.step.clash.out.list",
          label: "Triaged clash list",
        },
        {
          labelKey:
            "cases.coordinate_models_and_clashes.step.clash.out.grouped",
          label: "Conflicts by system",
        },
      ],
      titleKey: "cases.coordinate_models_and_clashes.step.clash.title",
      titleDefault: "Run and triage the clash test",
      whatKey: "cases.coordinate_models_and_clashes.step.clash.what",
      whatDefault:
        "Run the tests between the disciplines that actually interfere, group the hits by system, and strip out the tolerance touches, insulation overlaps and duplicates so a workable list remains.",
      whyKey: "cases.coordinate_models_and_clashes.step.clash.why",
      whyDefault:
        "A raw run returns thousands of hits and nobody opens it twice. Triage is what turns that dump into the handful of real conflicts a coordination meeting can actually decide on.",
      moduleLabel: "Clash detection",
      moduleLabelKey: "nav.clash",
      to: "/clash",
    },
    {
      id: "resolve",
      icon: "AlertTriangle",
      inputs: [
        {
          labelKey: "cases.coordinate_models_and_clashes.step.resolve.in.list",
          label: "Triaged clash list",
        },
        {
          labelKey:
            "cases.coordinate_models_and_clashes.step.resolve.in.owners",
          label: "Discipline owners",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.coordinate_models_and_clashes.step.resolve.out.issues",
          label: "Tracked clash issues",
        },
        {
          labelKey:
            "cases.coordinate_models_and_clashes.step.resolve.out.cleared",
          label: "Cleared re-run",
        },
        {
          labelKey:
            "cases.coordinate_models_and_clashes.step.resolve.out.models",
          label: "Corrected models",
        },
      ],
      titleKey: "cases.coordinate_models_and_clashes.step.resolve.title",
      titleDefault: "Drive the conflicts to closure",
      whatKey: "cases.coordinate_models_and_clashes.step.resolve.what",
      whatDefault:
        "Raise each surviving conflict as a tracked issue, assign it to the discipline that owns the fix, and follow it through re-issue until the corrected model clears the re-run.",
      whyKey: "cases.coordinate_models_and_clashes.step.resolve.why",
      whyDefault:
        "A duct clashing a beam is a ten-minute model edit today. Discovered on site with the steel already up, it becomes a rework order, a variation and a hole in the programme.",
      moduleLabel: "Non-conformance",
      moduleLabelKey: "nav.ncr",
      to: "/projects/:projectId/ncr",
    },
  ],
};

export default playbook;
