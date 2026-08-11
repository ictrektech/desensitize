FROM nvcr.io/nvidia/pytorch:25.08-py3

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libxcb1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
COPY docker/constraints.nvidia-arm.txt /tmp/constraints.nvidia-arm.txt
COPY docker/modules/onnxruntime_gpu-1.27.0-cp312-cp312-linux_aarch64.whl /tmp/
RUN PIP_CONSTRAINT=/tmp/constraints.nvidia-arm.txt pip3 install --no-cache-dir -r requirements.txt \
    && pip3 uninstall -y onnxruntime || true \
    && pip3 install --force-reinstall --no-deps /tmp/onnxruntime_gpu-1.27.0-cp312-cp312-linux_aarch64.whl \
    && rm /tmp/onnxruntime_gpu-1.27.0-cp312-cp312-linux_aarch64.whl /tmp/constraints.nvidia-arm.txt
COPY app ./app
EXPOSE 5000
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
