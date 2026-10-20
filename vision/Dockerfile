# 独立部署用的识别服务镜像（CPU 版）。
# 构建（在 vision/ 目录下）：
#   docker build -t fridge-vision .
# 运行：
#   docker run --rm -p 8770:8770 \
#     -e FRIDGE_VISION_TOKEN=换成你自己的令牌 \
#     -v fridge-vision-data:/data \
#     fridge-vision
#
# 说明：
# - 权重文件不打进 Git，构建前确认 weights/yolov8s.pt 存在（或改 COPY 只带需要的权重）。
# - CPU 推理单张约 1–3 秒，演示够用；有 GPU 请改用 requirements-torch-cu128.txt 并挂载显卡。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRIDGE_VISION_RUNTIME_DIR=/data

# OpenCV / Ultralytics 需要的系统库
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/fridge-vision

COPY requirements-torch-cpu.txt ./
RUN pip install -r requirements-torch-cpu.txt

COPY pyproject.toml ./
COPY src ./src
RUN pip install -e .

COPY configs ./configs
COPY weights ./weights

VOLUME ["/data"]
EXPOSE 8770

CMD ["python", "-m", "food_recognition.server", "--host", "0.0.0.0", "--port", "8770", "--device", "auto"]
