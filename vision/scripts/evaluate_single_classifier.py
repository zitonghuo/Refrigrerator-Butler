# -*- coding: utf-8 -*-
"""Evaluate a single-item classifier on an ImageFolder-style test directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


class FolderDataset(Dataset):
    def __init__(self, root: Path, class_to_idx: dict[str, int]):
        self.items = []
        for folder in sorted(root.iterdir()):
            if folder.is_dir() and folder.name in class_to_idx:
                self.items.extend((p, class_to_idx[folder.name]) for p in folder.glob("*.jpg"))
        self.tf = transforms.Compose([
            transforms.Resize(256), transforms.CenterCrop(224),
            transforms.ToTensor(), transforms.Normalize(MEAN, STD),
        ])

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        path, label = self.items[i]
        with Image.open(path) as im:
            return self.tf(im.convert("RGB")), label


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--device", default="0")
    parser.add_argument("--output", type=Path, default=Path("outputs/classifier_eval.json"))
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() and args.device != "cpu" else "cpu")
    ckpt = torch.load(args.checkpoint, map_location=device)
    classes = ckpt["classes"]
    model = torch.hub.load("pytorch/vision", "resnet18", weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, len(classes))
    model.load_state_dict(ckpt["state_dict"])
    model.to(device).eval()

    ds = FolderDataset(args.data, {c: i for i, c in enumerate(classes)})
    loader = DataLoader(ds, batch_size=64, shuffle=False, num_workers=2)
    correct1 = correct3 = total = 0
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            pred = model(images).topk(3, dim=1).indices
            total += labels.numel()
            correct1 += (pred[:, 0] == labels).sum().item()
            correct3 += pred.eq(labels.view(-1, 1)).any(dim=1).sum().item()
    report = {"images": total, "top1": round(correct1 / total, 4), "top3": round(correct3 / total, 4)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
