"""
gRPC 测试辅助模块
封装 mock gRPC Echo Server 的启停和 gRPC 客户端调用
"""

import sys
import time
import subprocess
import json
from pathlib import Path


_server_proc = None
_GRPC_MOCK_DIR = str(Path(__file__).resolve().parent.parent / "grpc_mock")


def start_grpc_server(port=19090, timeout=3):
    """
    启动 mock gRPC Echo Server

    Args:
        port: 监听端口
        timeout: 等待启动超时秒数

    Returns:
        subprocess.Popen: 服务进程对象

    Raises:
        RuntimeError: 启动失败
    """
    global _server_proc

    if _server_proc is not None and _server_proc.poll() is None:
        stop_grpc_server()

    server_script = str(Path(_GRPC_MOCK_DIR) / "server.py")
    _server_proc = subprocess.Popen(
        [sys.executable, server_script, str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(timeout)

    if _server_proc.poll() is not None:
        stderr = _server_proc.stderr.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"gRPC mock server 启动失败: {stderr}")

    return _server_proc


def stop_grpc_server():
    """停止 mock gRPC Echo Server"""
    global _server_proc
    if _server_proc is not None:
        _server_proc.terminate()
        try:
            _server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _server_proc.kill()
        _server_proc = None


def grpc_call(target, message="hello", metadata=None, timeout=5):
    """
    调用 gRPC Echo 服务并返回结果

    Args:
        target: gRPC 服务地址 (如 "127.0.0.1:19080")
        message: 请求消息
        metadata: 附加的 metadata dict (可选)
        timeout: 调用超时秒数

    Returns:
        dict: {"message": str, "received_metadata": dict}

    Raises:
        Exception: gRPC 调用失败
    """
    import grpc
    grpc_mock_dir = _GRPC_MOCK_DIR
    if grpc_mock_dir not in sys.path:
        sys.path.insert(0, grpc_mock_dir)

    import echo_pb2
    import echo_pb2_grpc

    channel = grpc.insecure_channel(target)
    stub = echo_pb2_grpc.EchoServiceStub(channel)

    md = []
    if metadata:
        for k, v in metadata.items():
            md.append((k, v))

    response = stub.Echo(
        echo_pb2.EchoRequest(message=message),
        metadata=md or None,
        timeout=timeout,
    )

    result = {
        "message": response.message,
        "received_metadata": dict(response.received_metadata),
    }
    channel.close()
    return result
