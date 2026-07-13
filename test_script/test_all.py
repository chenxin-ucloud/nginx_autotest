"""
统一测试脚本
读取合并后的 test_data/test_data.yaml，执行所有非 gRPC 测试用例。
gRPC 用例（grpc_set_header）因需独立 mock server fixture，保留在 test_grpc_set_header.py。
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
from comms.log_utils import logger


# 读取合并后的测试数据
test_data = read_yaml(get_test_data_path("test_data.yaml"))

# 读取Nginx配置路径
try:
    nginx_path = read_config("nginx", "nginx_path")
    nginx_bin_path = read_config("nginx", "nginx_bin_path")
except Exception as e:
    logger.warning(f"读取Nginx配置路径失败，使用默认路径。错误: {str(e)}")
    nginx_path = "/etc/nginx/nginx.conf"
    nginx_bin_path = "/usr/sbin/nginx"


@pytest.mark.parametrize("case_id, case_info", test_data.items())
def test_case(case_id, case_info):
    """
    通用测试用例执行函数

    断言模式：
    - expect_syntax_fail: 语法检查必须失败，expected_result 中的串需出现在失败输出中
    - operate_steps: 每条命令独立断言，expected 仅对该命令输出校验，unexpected 不应出现
    - 旧格式（operate_commands+扁平expected/unexpected）: 回退到合并输出断言

    Args:
        case_id: 用例ID
        case_info: 用例信息字典
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

        if case_info.get("expect_syntax_fail"):
            # 语法校验类用例：预期语法检查失败
            if success:
                raise AssertionError("预期语法检查失败但实际通过")
            logger.info("语法检查按预期失败")
            for expected in case_info["expected_result"]:
                assert expected in output, f"语法失败输出未包含预期: {expected}"
            logger.info(f"[{case_id}] {case_info['test_purpose']} 执行成功！")
            return

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

        # 4. 执行测试命令并断言
        if "operate_steps" in case_info:
            # 新格式：每命令独立断言
            for step in case_info["operate_steps"]:
                cmd = step["command"]
                logger.info(f"执行: {cmd}")
                result = run_nginx_cmd(cmd)
                logger.info(f"输出: {result[:200]}..." if len(result) > 200 else f"输出: {result}")
                for expected in step.get("expected", []):
                    assert expected in result, f"命令[{cmd}]输出未包含预期: {expected}"
                for unexpected in step.get("unexpected", []):
                    assert unexpected not in result, f"命令[{cmd}]输出不应包含: {unexpected}"
                logger.info(f"命令[{cmd}] 断言通过")
        else:
            # 旧格式回退：合并输出断言
            logger.info("执行测试命令(旧格式合并断言)...")
            all_output = ""
            for cmd in case_info["operate_commands"]:
                logger.info(f"执行: {cmd}")
                result = run_nginx_cmd(cmd)
                all_output += result + "\n"
                logger.info(f"输出: {result[:200]}..." if len(result) > 200 else f"输出: {result}")
            for expected in case_info["expected_result"]:
                assert expected in all_output, f"结果验证失败！预期包含: {expected}"
            if "unexpected_result" in case_info:
                for unexpected in case_info["unexpected_result"]:
                    assert unexpected not in all_output, \
                        f"优先级验证失败！响应中不应包含: {unexpected}"

        logger.info(f"[{case_id}] {case_info['test_purpose']} 执行成功！")

    except AssertionError as e:
        logger.error(f"用例 {case_id} 断言失败: {str(e)}")
        raise

    except Exception as e:
        logger.error(f"用例 {case_id} 执行异常: {str(e)}")
        # 读取Nginx错误日志，辅助排查
        try:
            error_log = read_nginx_error_log(10)
            logger.error(f"Nginx错误日志（最新10行）:\n{error_log}")
        except Exception as log_error:
            logger.error(f"读取Nginx错误日志失败: {str(log_error)}")
        raise
