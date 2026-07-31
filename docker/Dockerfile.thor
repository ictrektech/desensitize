FROM nvcr.io/nvidia/pytorch:25.08-py3

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
COPY docker/modules/onnxruntime_gpu-1.27.0-cp312-cp312-linux_aarch64.whl /tmp/
RUN pip3 install --no-cache-dir -r requirements.txt \
    && pip3 install --force-reinstall --no-deps /tmp/onnxruntime_gpu-1.27.0-cp312-cp312-linux_aarch64.whl \
    && rm /tmp/onnxruntime_gpu-1.27.0-cp312-cp312-linux_aarch64.whl
COPY app ./app
EXPOSE 5000
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
