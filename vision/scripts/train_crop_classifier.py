# -*- coding: utf-8 -*-
"""Train a 45-class produce crop classifier (GT-box upper-bound experiment)."""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import models, transforms
from PIL import Image

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


class CropDataset(Dataset):
    def __init__(self, root: Path, class_to_idx: dict[str, int], transform):
        self.items = []
        self.transform = transform
        for folder in sorted(root.iterdir()):
            if not folder.is_dir() or folder.name not in class_to_idx:
                continue
            for image in folder.glob("*.jpg"):
                self.items.append((image, class_to_idx[folder.name]))

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        path, label = self.items[index]
        with Image.open(path) as im:
            image = im.convert("RGB")
        return self.transform(image), label


def evaluate(model, loader, device):
    model.eval()
    top1 = top3 = total = 0
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            logits = model(images)
            _, pred = logits.topk(3, dim=1)
            total += labels.numel()
            top1 += (pred[:, 0] == labels).sum().item()
            top3 += pred.eq(labels.view(-1, 1)).any(dim=1).sum().item()
    return top1 / total, top3 / total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\china_fridge_produce_crops_v1"))
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--device", default="0")
    parser.add_argument("--output", type=Path, default=Path("runs/crop_classifier_v1"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() and args.device != "cpu" else "cpu")
    train_dir = args.data / "train"
    folders = sorted(p.name for p in train_dir.iterdir() if p.is_dir())
    class_to_idx = {name: i for i, name in enumerate(folders)}
    print("classes", len(folders))

    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.65, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(10),
        transforms.ColorJitter(0.25, 0.25, 0.2, 0.05),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    eval_tf = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])

    train_ds = CropDataset(train_dir, class_to_idx, train_tf)
    val_ds = CropDataset(args.data / "val", class_to_idx, eval_tf)
    test_ds = CropDataset(args.data / "test", class_to_idx, eval_tf)
    counts = Counter(label for _, label in train_ds.items)
    weights = [1.0 / counts[label] for _, label in train_ds.items]
    sampler = WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)
    train_loader = DataLoader(train_ds, batch_size=args.batch, sampler=sampler, num_workers=args.workers, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch, shuffle=False, num_workers=args.workers, pin_memory=True)
    test_loader = DataLoader(test_ds, batch_size=args.batch, shuffle=False, num_workers=args.workers, pin_memory=True)
    print("train/val/test", len(train_ds), len(val_ds), len(test_ds))

    try:
        model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    except Exception as exc:  # offline fallback
        print("pretrained weights unavailable:", exc)
        model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, len(folders))
    if args.resume and (args.output / "best.pt").exists():
        checkpoint = torch.load(args.output / "best.pt", map_location=device)
        model.load_state_dict(checkpoint["state_dict"])
        print("resumed from", args.output / "best.pt")
    model = model.to(device)

    criterion = nn.CrossEntropyLoss(label_smoothing=0.05)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")

    best = 0.0
    history = []
    args.output.mkdir(parents=True, exist_ok=True)
    for epoch in range(1, args.epochs + 1):
        model.train()
        running = 0.0
        seen = 0
        started = time.time()
        for images, labels in train_loader:
            images, labels = images.to(device, non_blocking=True), labels.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                loss = criterion(model(images), labels)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            running += loss.item() * labels.numel()
            seen += labels.numel()
        scheduler.step()
        val1, val3 = evaluate(model, val_loader, device)
        history.append({"epoch": epoch, "loss": running / seen, "val_top1": val1, "val_top3": val3, "seconds": round(time.time() - started, 1)})
        print(history[-1])
        if val1 > best:
            best = val1
            torch.save({"state_dict": model.state_dict(), "classes": folders, "val_top1": val1}, args.output / "best.pt")
    checkpoint = torch.load(args.output / "best.pt", map_location=device)
    model.load_state_dict(checkpoint["state_dict"])
    test1, test3 = evaluate(model, test_loader, device)
    metrics = {
        "classes": len(folders),
        "train": len(train_ds), "val": len(val_ds), "test": len(test_ds),
        "best_val_top1": best, "test_top1": test1, "test_top3": test3,
        "history": history,
    }
    (args.output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
