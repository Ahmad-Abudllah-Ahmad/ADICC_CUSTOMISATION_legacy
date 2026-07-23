// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Coordinate and resolve model clashes".
//
// A BIM coordination case: federate the discipline models, run clash
// detection, triage and assign the real clashes, raise the design questions
// they create and confirm they are resolved in the next model issue. Content
// strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "coordinate-and-resolve-model-clashes",
  order: 268,
  category: "bim",
  companyTypes: ["bim-consultant", "designer", "general-contractor"],
  icon: "Crosshair",
  titleKey: "cases.coordinate_and_resolve_model_clashes.title",
  titleDefault: "Coordinate and resolve model clashes",
  descKey: "cases.coordinate_and_resolve_model_clashes.desc",
  descDefault:
    "Run a clash coordination round: federate the discipline models, detect the clashes, triage and assign the real ones, raise the design questions they create and confirm they are resolved in the next model issue.",
  estMinutes: 12,
  steps: [
    {
      id: "federate",
      icon: "Layers",
      inputs: [
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.federate.in.models",
          label: "Discipline models",
        },
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.federate.in.origin",
          label: "Shared project origin",
        },
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.federate.in.revisions",
          label: "Current revisions",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.federate.out.federated",
          label: "Federated model set",
        },
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.federate.out.aligned",
          label: "Revision-checked models",
        },
      ],
      titleKey:
        "cases.coordinate_and_resolve_model_clashes.step.federate.title",
      titleDefault: "Federate the discipline models",
      whatKey: "cases.coordinate_and_resolve_model_clashes.step.federate.what",
      whatDefault:
        "Bring the latest architecture, structure and services models together into one federated set on the shared project origin, and confirm each discipline is the current revision before you test anything.",
      whyKey: "cases.coordinate_and_resolve_model_clashes.step.federate.why",
      whyDefault:
        "Clash results are only as good as the models behind them. Coordinating against a stale or misaligned model wastes a whole round chasing conflicts that are already fixed or that do not really exist.",
      moduleLabel: "Federations",
      moduleLabelKey: "nav.federations",
      to: "/bim/federations",
    },
    {
      id: "detect",
      icon: "Crosshair",
      inputs: [
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.detect.in.federated",
          label: "Federated model set",
        },
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.detect.in.rules",
          label: "Clash test rules",
        },
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.detect.in.tolerances",
          label: "Tolerance settings",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.detect.out.results",
          label: "Raw clash results",
        },
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.detect.out.report",
          label: "Clash test report",
        },
      ],
      titleKey: "cases.coordinate_and_resolve_model_clashes.step.detect.title",
      titleDefault: "Run clash detection",
      whatKey: "cases.coordinate_and_resolve_model_clashes.step.detect.what",
      whatDefault:
        "Run the clash tests between the disciplines that matter, structure against services, services against ceilings, and let the tolerances filter out the touch-and-graze noise so the real conflicts stand out.",
      whyKey: "cases.coordinate_and_resolve_model_clashes.step.detect.why",
      whyDefault:
        "A pipe through a beam or a duct through a wall costs far more to fix on site than in the model. Detection is where you catch it while it is still a line on a screen and not a change order.",
      moduleLabel: "Clash detection",
      moduleLabelKey: "nav.clash",
      to: "/clash",
    },
    {
      id: "triage",
      icon: "ListChecks",
      inputs: [
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.triage.in.results",
          label: "Raw clash results",
        },
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.triage.in.model",
          label: "3D model view",
        },
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.triage.in.owners",
          label: "Discipline owners",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.triage.out.issues",
          label: "Grouped clash issues",
        },
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.triage.out.assigned",
          label: "Owner assignments",
        },
      ],
      titleKey: "cases.coordinate_and_resolve_model_clashes.step.triage.title",
      titleDefault: "Triage and assign the real clashes",
      whatKey: "cases.coordinate_and_resolve_model_clashes.step.triage.what",
      whatDefault:
        "Group the raw hits into genuine issues, drop the false positives, and assign each real clash to the discipline that owns the fix with a clear view of where it sits in the model.",
      whyKey: "cases.coordinate_and_resolve_model_clashes.step.triage.why",
      whyDefault:
        "A raw clash count of thousands helps nobody. The value is in a short, owned list where every item is a real conflict with a name against it, so the coordination meeting is about decisions, not sorting.",
      moduleLabel: "3D model",
      moduleLabelKey: "nav.bim",
      to: "/projects/:projectId/bim",
    },
    {
      id: "raise",
      icon: "MessageSquare",
      inputs: [
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.raise.in.clashes",
          label: "Design-blocking clashes",
        },
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.raise.in.viewpoint",
          label: "Model viewpoint",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.raise.out.rfi",
          label: "Raised RFI",
        },
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.raise.out.record",
          label: "Traceable design question",
        },
      ],
      titleKey: "cases.coordinate_and_resolve_model_clashes.step.raise.title",
      titleDefault: "Raise the design questions",
      whatKey: "cases.coordinate_and_resolve_model_clashes.step.raise.what",
      whatDefault:
        "Where a clash needs a design decision rather than a simple move, raise it as an RFI to the design lead so the answer is written down, dated and traceable back to the model view.",
      whyKey: "cases.coordinate_and_resolve_model_clashes.step.raise.why",
      whyDefault:
        "Some clashes cannot be closed by a coordinator alone, they need a real design call. Raising them formally means the decision is on record and the model change that follows can be traced to the reason for it.",
      moduleLabel: "RFI",
      moduleLabelKey: "nav.rfi",
      to: "/projects/:projectId/rfi",
    },
    {
      id: "confirm",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.confirm.in.revision",
          label: "Next model revision",
        },
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.confirm.in.assigned",
          label: "Assigned clashes",
        },
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.confirm.in.answers",
          label: "RFI answers",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.confirm.out.verified",
          label: "Verified closures",
        },
        {
          labelKey:
            "cases.coordinate_and_resolve_model_clashes.step.confirm.out.report",
          label: "Coordination round report",
        },
      ],
      titleKey: "cases.coordinate_and_resolve_model_clashes.step.confirm.title",
      titleDefault: "Confirm resolution in the next issue",
      whatKey: "cases.coordinate_and_resolve_model_clashes.step.confirm.what",
      whatDefault:
        "When the next model revision comes in, re-run the tests, check the assigned clashes are actually gone, and report the round with what closed, what is still open and what carried over.",
      whyKey: "cases.coordinate_and_resolve_model_clashes.step.confirm.why",
      whyDefault:
        "Coordination is not done when a fix is promised, it is done when the next model proves it. Re-running and reporting each round is what shows the trend to zero and keeps everyone honest about progress.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
