"""
全局夹具模块（conftest.py）
封装所有测试用例的公共前置/后置操作
"""

import pytest
from comms.nginx_operate import (
    reload_nginx,
    backup_nginx_config,
    restore_nginx_config,
    ensure_local_dns,
)
from comms.log_utils import logger


@pytest.fixture(scope="session", autouse=True)
def global_fixture():
    """
    全局前置/后置操作：
    - 所有用例执行前，备份Nginx原始配置
    - 所有用例执行完成后，恢复Nginx原始配置
    """
    logger.info("测试会话开始")

    # 前置操作：配置测试域名 DNS 解析（match_http_host 用例以域名形式请求）
    try:
        ensure_local_dns()
    except Exception as e:
        logger.warning(f"测试域名 DNS 配置失败: {str(e)}（match_http_host 域名形式用例可能无法解析）")

    # 前置操作：备份配置
    try:
        backup_path = backup_nginx_config()
        logger.info(f"Nginx配置已备份: {backup_path}")
    except Exception as e:
        logger.warning(f"Nginx配置备份失败: {str(e)}")
        logger.warning("建议手动备份后再执行测试！")

    yield  # 执行测试用例

    # 后置操作：恢复配置
    logger.info("测试执行完毕，开始清理配置")

    try:
        restore_nginx_config()
        logger.info("Nginx配置已恢复")
    except Exception as e:
        logger.error(f"Nginx配置恢复失败: {str(e)}")
        logger.error("请手动恢复Nginx配置！")

    logger.info("测试会话结束")


@pytest.fixture(scope="module", autouse=True)
def module_fixture():
    """
    模块级前置/后置操作
    每个测试模块执行前后调用：
    - 前置：恢复到原始配置
    - 后置：恢复到原始配置
    """
    logger.info("开始执行当前模块测试")
    # 模块前置：恢复原始配置
    try:
        restore_nginx_config()
        reload_nginx()
    except Exception:
        pass

    yield

    # 模块后置：恢复配置
    try:
        restore_nginx_config()
        reload_nginx()
    except Exception:
        pass

    logger.info("当前模块测试执行完成")


@pytest.fixture(scope="function")
def case_fixture():
    """
    用例级前置/后置操作（可选）
    每个测试用例执行前后调用
    """
    # 用例前置操作
    yield
    # 用例后置操作
    # 可以在这里添加用例级别的清理操作
