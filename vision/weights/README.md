# Model Weights

Model weights are **not tracked in Git**. Download them from the GitHub Releases
page:

https://github.com/zitonghuo/Refrigrerator-Butler/releases/latest

## Current default

```text
fruits_vegetables_yolov8m_seg_expanded_v4.pt
```

- Size: 52.3 MB
- SHA256: `F0B7163636FD25DE502D9B12745CB09F32DC2249F91A32EF035A2D74B8214E5B`
- Trained on IntAli + AICook + DFV16 SAM-seg data
- YOLOv8m-seg, **61-class** head, 640 input
- Release asset:
  https://github.com/zitonghuo/Refrigrerator-Butler/releases/download/models-v1/fruits_vegetables_yolov8m_seg_expanded_v4.pt

Place it at:

```text
vision/weights/fruits_vegetables_yolov8m_seg_expanded_v4.pt
```

If this file is absent, the server falls back to the previous
`fruits_vegetables_yolov8m_seg_dfv16_v3.pt` checkpoint when available.

Verify on Windows:

```powershell
(Get-FileHash .\vision\weights\fruits_vegetables_yolov8m_seg_expanded_v4.pt -Algorithm SHA256).Hash
```

## Rollback

The previous 47-class DFV16 m-seg detector:

```text
fruits_vegetables_yolov8m_seg_dfv16_v3.pt
```

The earlier 47-class m-seg detector:

```text
fruits_vegetables_yolov8m_seg_aicook_v1.pt
```

The older detection fallback:

```text
fruits_vegetables_yolov8s_cn_v2.pt
```

Start the service with either explicit checkpoint:

```powershell
python -m food_recognition.server `
  --produce-weights weights/fruits_vegetables_yolov8m_seg_aicook_v1.pt
```

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
