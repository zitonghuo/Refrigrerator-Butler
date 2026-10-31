# -*- coding: utf-8 -*-
"""Prune rare non-Chinese-household classes from the produce detector head.

Only the class branch is changed; box regression weights stay untouched.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", type=Path, default=Path("weights/fruits_vegetables_yolov8s_v1.pt"))
    parser.add_argument("--config", type=Path, default=Path("configs/china_household_filter_v1.json"))
    parser.add_argument("--output", type=Path, default=Path("weights/fruits_vegetables_yolov8s_cn_v2.pt"))
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    blocked = set(config["blocked_model_labels"])
    model = YOLO(str(args.weights))
    names = model.names
    keep = [i for i in sorted(names) if names[i] not in blocked]
    blocked_present = [names[i] for i in sorted(names) if names[i] in blocked]
    missing = sorted(blocked - set(blocked_present))
    if missing:
        raise SystemExit(f"blocked labels not found in model: {missing}")

    head = model.model.model[-1]
    if head.nc != len(names):
        raise SystemExit(f"unexpected head.nc={head.nc}, names={len(names)}")
    old_nc = head.nc
    new_nc = len(keep)

    for branch in head.cv3:
        last = branch[-1]
        conv = last.conv if hasattr(last, "conv") else last
        new_conv = torch.nn.Conv2d(
            conv.in_channels,
            new_nc,
            kernel_size=conv.kernel_size,
            stride=conv.stride,
            padding=conv.padding,
            dilation=conv.dilation,
            groups=conv.groups,
            bias=conv.bias is not None,
            padding_mode=conv.padding_mode,
        )
        with torch.no_grad():
            new_conv.weight.copy_(conv.weight[keep])
            if conv.bias is not None and new_conv.bias is not None:
                new_conv.bias.copy_(conv.bias[keep])
        if hasattr(last, "conv"):
            last.conv = new_conv
        else:
            branch[-1] = new_conv

    kept_names = {new_index: names[old_index] for new_index, old_index in enumerate(keep)}
    head.nc = new_nc
    head.no = 4 * head.reg_max + new_nc
    head.names = kept_names
    model.model.nc = new_nc
    model.model.names = kept_names
    model.model.yaml["nc"] = new_nc
    model.model.yaml["names"] = kept_names

    args.output.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(args.output))
    print(json.dumps({
        "input": str(args.weights),
        "output": str(args.output),
        "old_nc": old_nc,
        "new_nc": new_nc,
        "removed": blocked_present,
        "kept": list(kept_names.values()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
