"""
grpc_set_header模块测试脚本
负责执行grpc_set_header模块的测试用例，支持端到端gRPC功能验证
"""

import pytest
from comms.constants import get_test_data_path
from comms.data_read import read_yaml, read_config
from comms.nginx_operate import (
    add_nginx_config,
    check_nginx_config,
    reload_nginx,
    restart_nginx,
    read_nginx_error_log,
    run_nginx_cmd,
)
from comms.cmd_operate import run_cmd
from comms.grpc_helper import start_grpc_server, stop_grpc_server, grpc_call
from comms.log_utils import logger


test_data = read_yaml(get_test_data_path("grpc_set_header.yaml"))

try:
    nginx_path = read_config("nginx", "nginx_path")
    nginx_bin_path = read_config("nginx", "nginx_bin_path")
except Exception as e:
    logger.warning(f"读取Nginx配置路径失败，使用默认路径。错误: {str(e)}")
    nginx_path = "/etc/nginx/nginx.conf"
    nginx_bin_path = "/usr/sbin/nginx"


@pytest.fixture(scope="module", autouse=True)
def grpc_server():
    """模块级别 fixture：启动/停止 gRPC mock server"""
    start_grpc_server(port=19090)
    logger.info("gRPC mock server 已启动 (port 19090)")
    yield
    stop_grpc_server()
    logger.info("gRPC mock server 已停止")


@pytest.mark.parametrize("case_id, case_info", test_data.items())
def test_grpc_set_header(case_id, case_info):
    """
    grpc_set_header模块自动化测试用例
    """
    logger.info(f"开始执行 [{case_id}] {case_info['test_purpose']}")

    try:
        # 1. 添加Nginx测试配置
        logger.info("添加Nginx测试配置...")
        add_nginx_config(nginx_path, case_info["config_content"])
        logger.info("配置添加成功")

        # 2. 检查Nginx配置语法
        logger.info("检查Nginx配置语法...")
        success, output = check_nginx_config()
        logger.info(f"输出: {output}")
        if not success:
            raise AssertionError(f"Nginx配置语法检查失败: {output}")
        logger.info("配置语法检查通过")

        # 3. 重新加载Nginx配置
        logger.info("重新加载Nginx配置...")
        success, output = reload_nginx()
        if not success:
            logger.warning(f"Nginx重新加载失败: {output}")
            success, output = restart_nginx()
            if not success:
                raise AssertionError(f"Nginx重启失败: {output}")
        logger.info("Nginx配置重新加载成功")

        # 4. 执行测试命令
        logger.info("执行测试命令...")
        all_output = ""
        for cmd in case_info["operate_commands"]:
            logger.info(f"执行: {cmd}")
            result = run_nginx_cmd(cmd)
            all_output += result + "\n"
            logger.info(f"输出: {result[:200]}..." if len(result) > 200 else f"输出: {result}")

        # 5. 验证命令输出预期结果
        logger.info("验证预期结果...")
        for expected in case_info["expected_result"]:
            assert expected in all_output, f"结果验证失败！预期包含: {expected}"
        logger.info("所有预期结果验证通过")

        # 6. gRPC 端到端功能验证
        if "grpc_verify" in case_info:
            verify = case_info["grpc_verify"]
            target = verify["target"]
            message = verify.get("message", "test")

            client_metadata = verify.get("client_metadata")

            logger.info("gRPC 端到端功能验证...")
            logger.info(f"调用目标: {target}, 消息: {message}")
            if client_metadata:
                logger.info(f"客户端 metadata: {client_metadata}")

            result = grpc_call(target, message, metadata=client_metadata)
            metadata = result["received_metadata"]
            logger.info(f"响应消息: {result['message']}")
            logger.info(f"收到的 metadata: {metadata}")

            assert result["message"] == message, \
                f"响应消息不匹配！预期: {message}, 实际: {result['message']}"

            if "expect_metadata" in verify:
                for key, value in verify["expect_metadata"].items():
                    actual = metadata.get(key)
                    assert actual == value, \
                        f"metadata 验证失败！{key}: 预期={value}, 实际={actual}"
                    logger.info(f"{key}: {actual}")

            if "unexpected_metadata" in verify:
                for key in verify["unexpected_metadata"]:
                    assert key not in metadata, \
                        f"metadata 不应包含 {key}，但实际存在: {metadata.get(key)}"
                    logger.info(f"{key} 未出现在 metadata 中")

            logger.info("gRPC 端到端验证通过")

        logger.info(f"[{case_id}] {case_info['test_purpose']} 执行成功！")

    except AssertionError as e:
        logger.error(f"用例 {case_id} 断言失败: {str(e)}")
        raise

    except Exception as e:
        logger.error(f"用例 {case_id} 执行异常: {str(e)}")
        try:
            error_log = read_nginx_error_log(10)
            logger.error(f"Nginx错误日志（最新10行）:\n{error_log}")
        except Exception as log_error:
            logger.error(f"读取Nginx错误日志失败: {str(log_error)}")
        raise
