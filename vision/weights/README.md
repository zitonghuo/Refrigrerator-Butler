# Model Weights

Model weights are **not tracked in Git**. Download them from the GitHub Releases
page:

https://github.com/zitonghuo/Refrigrerator-Butler/releases/latest

## Current default

```text
fruits_vegetables_yolov8m_seg_aicook_v1.pt
```

- Size: 52.3 MB
- SHA256: `E571ADB223D04C6717C12F04295527EF98B23B87C234971C18BF37AA6F9D7B55`
- Trained on IntAli + AICook produce data
- YOLOv8m-seg, 47-class head, 640 input

Place it at:

```text
vision/weights/fruits_vegetables_yolov8m_seg_aicook_v1.pt
```

Verify on Windows:

```powershell
(Get-FileHash .\vision\weights\fruits_vegetables_yolov8m_seg_aicook_v1.pt -Algorithm SHA256).Hash
```

## Rollback

The previous 47-class detector remains available as a rollback:

```text
fruits_vegetables_yolov8s_cn_v2.pt
```

Start the service with:

```powershell
python -m food_recognition.server `
  --produce-weights weights/fruits_vegetables_yolov8s_cn_v2.pt
```

## Release checklist

1. GitHub → Releases → Draft a new release.
2. Tag it `models-v1`.
3. Upload the `.pt` file with the exact filename above.
4. Publish.
5. Confirm the asset URL is reachable without GitHub login.
