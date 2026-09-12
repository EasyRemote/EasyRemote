# Linux verification of resident-host framing, not an official-Hub E2E image.
FROM python:3.12-slim
RUN pip install --no-cache-dir \
    pytest==9.0.2 pytest-asyncio==1.3.0 \
    grpcio==1.83.0 protobuf==7.35.1 cryptography==48.0.1 \
    numpy==2.5.3 pydantic==2.13.4
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/src/EasyRemote:/src/EasyNet-Cli/sdk/python:/src/EasyNet-Axon/sdk/python
WORKDIR /src/EasyRemote
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_duplex.py", "tests/test_value_codec.py", "tests/test_host.py"]
