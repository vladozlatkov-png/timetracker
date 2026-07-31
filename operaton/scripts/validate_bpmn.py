#!/usr/bin/env python3
"""Pre-deploy sanity check for the BPMN models.

Catches the failures that are cheap here and expensive against a live engine:
malformed XML, sequence flows pointing at nothing, and — the one that silently
ruins the whole point of using a BPMN engine — flow nodes with no diagram
interchange, which render as an empty or broken diagram in Cockpit.
"""

from __future__ import annotations

import glob
import os
import sys
import xml.etree.ElementTree as ET

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"

FLOW_NODE_TAGS = (
    "startEvent", "endEvent", "userTask", "serviceTask", "callActivity",
    "exclusiveGateway", "parallelGateway", "inclusiveGateway",
    "boundaryEvent", "intermediateCatchEvent", "intermediateThrowEvent",
    "subProcess", "task", "businessRuleTask", "scriptTask", "sendTask", "receiveTask",
)


def check(path: str) -> list[str]:
    problems: list[str] = []
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return [f"XML is not well-formed: {exc}"]

    ids = {el.get("id") for el in root.iter() if el.get("id")}
    di_elements = {el.get("bpmnElement") for el in root.iter() if el.get("bpmnElement")}

    flow_nodes = [
        el.get("id")
        for tag in FLOW_NODE_TAGS
        for el in root.iter(f"{{{BPMN}}}{tag}")
    ]
    for node in flow_nodes:
        if node not in di_elements:
            problems.append(f"flow node {node!r} has no BPMNShape — it will not render")

    flows = {el.get("id") for el in root.iter(f"{{{BPMN}}}sequenceFlow")}
    edges = {el.get("bpmnElement") for el in root.iter(f"{{{BPMNDI}}}BPMNEdge")}
    for flow in sorted(flows - edges):
        problems.append(f"sequence flow {flow!r} has no BPMNEdge — it will not render")

    for flow in root.iter(f"{{{BPMN}}}sequenceFlow"):
        for attr in ("sourceRef", "targetRef"):
            if flow.get(attr) not in ids:
                problems.append(
                    f"sequence flow {flow.get('id')!r} {attr}={flow.get(attr)!r} does not resolve"
                )

    for boundary in root.iter(f"{{{BPMN}}}boundaryEvent"):
        if boundary.get("attachedToRef") not in ids:
            problems.append(
                f"boundary event {boundary.get('id')!r} attachedToRef does not resolve"
            )

    # An exclusive gateway with conditional outgoing flows and no default can
    # deadlock at runtime when no condition matches.
    for gw in root.iter(f"{{{BPMN}}}exclusiveGateway"):
        outgoing = [el.text for el in gw.iter(f"{{{BPMN}}}outgoing")]
        if len(outgoing) > 1 and not gw.get("default"):
            conditional = [
                f.get("id") for f in root.iter(f"{{{BPMN}}}sequenceFlow")
                if f.get("id") in outgoing
                and f.find(f"{{{BPMN}}}conditionExpression") is not None
            ]
            if conditional:
                problems.append(
                    f"exclusive gateway {gw.get('id')!r} branches on conditions but has "
                    f"no default flow — no matching condition will deadlock the instance"
                )

    return problems


def main() -> int:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = sorted(glob.glob(os.path.join(here, "bpmn", "*.bpmn")))
    if not files:
        print("no .bpmn files found", file=sys.stderr)
        return 1

    failed = False
    for path in files:
        problems = check(path)
        name = os.path.relpath(path, here)
        if problems:
            failed = True
            print(f"FAIL {name}")
            for p in problems:
                print(f"     {p}")
        else:
            print(f"ok   {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
