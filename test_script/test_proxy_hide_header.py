"""
proxy_hide_header模块测试脚本
负责执行proxy_hide_header模块的测试用例
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
)
from comms.cmd_operate import run_cmd
from comms.log_utils import logger


# 读取测试数据
test_data = read_yaml(get_test_data_path("proxy_hide_header.yaml"))

# 读取Nginx配置路径
try:
    nginx_path = read_config("nginx", "nginx_path")
    nginx_bin_path = read_config("nginx", "nginx_bin_path")
except Exception as e:
    logger.warning(f"读取Nginx配置路径失败，使用默认路径。错误: {str(e)}")
    nginx_path = "/etc/nginx/nginx.conf"
    nginx_bin_path = "/usr/sbin/nginx"


@pytest.mark.parametrize("case_id, case_info", test_data.items())
def test_proxy_hide_header(case_id, case_info):
    """
    proxy_hide_header模块自动化测试用例

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
        if not success:
            raise AssertionError(f"Nginx配置语法检查失败: {output}")
        logger.info("配置语法检查通过")

        # 3. 重新加载Nginx配置
        logger.info("重新加载Nginx配置...")
        success, output = reload_nginx()
        if not success:
            logger.warning(f"Nginx重新加载失败: {output}")
            # 尝试重启
            success, output = restart_nginx()
            if not success:
                raise AssertionError(f"Nginx重启失败: {output}")
        logger.info("Nginx配置重新加载成功")

        # 4. 执行测试命令
        logger.info("执行测试命令...")
        all_output = ""
        for cmd in case_info["operate_commands"]:
            logger.info(f"执行: {cmd}")
            # Nginx命令需要使用完整路径并在Nginx目录下执行
            if cmd.strip().startswith("nginx "):
                full_nginx_bin = read_config("nginx", "nginx_bin_path")
                cmd = cmd.replace("nginx ", f'{full_nginx_bin} ')
                result = run_cmd(cmd)
            else:
                result = run_cmd(cmd)
            all_output += result + "\n"
            logger.info(f"输出: {result[:200]}..." if len(result) > 200 else f"输出: {result}")

        # 5. 验证预期结果
        logger.info("验证预期结果...")
        for expected in case_info["expected_result"]:
            assert expected in all_output, f"结果验证失败！预期包含: {expected}"
        logger.info("所有预期结果验证通过")

        # 6. 验证不应出现的结果（隐藏头验证）
        if "unexpected_result" in case_info:
            logger.info("验证响应头已被隐藏...")
            for unexpected in case_info["unexpected_result"]:
                assert unexpected not in all_output, \
                    f"隐藏头验证失败！响应中不应包含: {unexpected}"
            logger.info("所有隐藏头验证通过")

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
