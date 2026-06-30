"""自定义规则语法校验测试脚本"""

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


test_data = read_yaml(get_test_data_path("custom_rule_validation.yaml"))

try:
    nginx_path = read_config("nginx", "nginx_path")
    nginx_bin_path = read_config("nginx", "nginx_bin_path")
except Exception as e:
    logger.warning(f"读取Nginx配置路径失败，使用默认路径。错误: {str(e)}")
    nginx_path = "/etc/nginx/nginx.conf"
    nginx_bin_path = "/usr/sbin/nginx"


@pytest.mark.parametrize("case_id, case_info", test_data.items())
def test_custom_rule_validation(case_id, case_info):
    logger.info(f"开始执行 [{case_id}] {case_info['test_purpose']}")

    try:
        logger.info("添加Nginx测试配置...")
        add_nginx_config(nginx_path, case_info["config_content"])
        logger.info("配置添加成功")

        logger.info("检查Nginx配置语法...")
        success, output = check_nginx_config()
        logger.info(f"输出: {output}")

        if case_info.get("expect_syntax_fail"):
            if success:
                raise AssertionError("预期语法检查失败但实际通过")
            logger.info("语法检查按预期失败")
            all_output = output
        else:
            if not success:
                raise AssertionError(f"Nginx配置语法检查失败: {output}")
            logger.info("配置语法检查通过")

            logger.info("重新加载Nginx配置...")
            success, output = reload_nginx()
            if not success:
                logger.warning(f"Nginx重新加载失败: {output}")
                success, output = restart_nginx()
                if not success:
                    raise AssertionError(f"Nginx重启失败: {output}")
            logger.info("Nginx配置重新加载成功")

            logger.info("执行测试命令...")
            all_output = ""
            for cmd in case_info["operate_commands"]:
                logger.info(f"执行: {cmd}")
                result = run_nginx_cmd(cmd)
                all_output += result + "\n"
                logger.info(f"输出: {result[:200]}..." if len(result) > 200 else f"输出: {result}")

        logger.info("验证预期结果...")
        for expected in case_info["expected_result"]:
            assert expected in all_output, f"结果验证失败！预期包含: {expected}"
        logger.info("所有预期结果验证通过")

        if "unexpected_result" in case_info:
            logger.info("验证不应命中的结果...")
            for unexpected in case_info["unexpected_result"]:
                assert unexpected not in all_output, \
                    f"优先级验证失败！响应中不应包含: {unexpected}"
            logger.info("所有优先级验证通过")

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
