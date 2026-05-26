"""
Nginx操作工具模块
封装Nginx核心操作：备份、恢复、检查配置、重启等
"""

import re
import shutil
import time
from pathlib import Path

from .data_read import read_config
from .cmd_operate import run_cmd, run_cmd_with_code
from .log_utils import logger


_backup_file_path = None


def _is_docker_mode():
    try:
        mode = read_config("nginx", "mode")
        return mode.strip().lower() == "docker"
    except Exception:
        return False


def _get_container_name():
    return read_config("nginx", "container_name")


def _build_nginx_cmd(cmd_str):
    if _is_docker_mode():
        container = _get_container_name()
        return f'docker exec {container} {cmd_str}'
    return cmd_str


def run_nginx_cmd(cmd_str):
    """
    执行命令，自动处理 nginx 命令的路径替换和 Docker 包裹。
    非 nginx 命令直接执行。
    """
    if cmd_str.strip().startswith("nginx "):
        nginx_bin = read_config("nginx", "nginx_bin_path")
        cmd_str = cmd_str.replace("nginx ", f'{nginx_bin} ', 1)
        if _is_docker_mode():
            config_path = read_config("nginx", "nginx_container_path")
            cmd_str = f'{cmd_str} -c {config_path}'
        cmd_str = _build_nginx_cmd(cmd_str)
    return run_cmd(cmd_str)


def backup_nginx_config():
    """
    备份Nginx原始配置（测试前置操作）

    Returns:
        str: 备份文件路径
    """
    global _backup_file_path

    nginx_path = Path(read_config("nginx", "nginx_path"))
    backup_dir = Path(read_config("nginx", "backup_path"))

    if not nginx_path.exists():
        raise FileNotFoundError(f"Nginx配置文件不存在: {nginx_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    _backup_file_path = str(backup_dir / f"nginx_backup_{timestamp}.conf")

    shutil.copy2(str(nginx_path), _backup_file_path)
    logger.info(f"Nginx配置已备份至: {_backup_file_path}")
    return _backup_file_path


def restore_nginx_config():
    """
    恢复Nginx原始配置（测试后置操作）

    Returns:
        bool: 是否恢复成功
    """
    global _backup_file_path

    if _backup_file_path is None or not Path(_backup_file_path).exists():
        backup_dir = Path(read_config("nginx", "backup_path"))

        if backup_dir.exists():
            backup_files = sorted(
                backup_dir.glob("nginx_backup_*.conf"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if backup_files:
                _backup_file_path = str(backup_files[0])

    if _backup_file_path is None or not Path(_backup_file_path).exists():
        logger.warning("未找到备份文件，无法恢复Nginx配置")
        return False

    try:
        nginx_path = read_config("nginx", "nginx_path")
    except Exception:
        logger.warning("无法读取nginx_path配置")
        return False

    shutil.copy2(_backup_file_path, nginx_path)
    logger.info(f"Nginx配置已从 {_backup_file_path} 恢复")
    reload_nginx()
    return True


def check_nginx_config():
    """
    执行nginx -t，检查配置语法

    Returns:
        tuple: (是否成功, 输出信息)
    """
    nginx_bin = read_config("nginx", "nginx_bin_path")

    if _is_docker_mode():
        config_path = read_config("nginx", "nginx_container_path")
    else:
        config_path = read_config("nginx", "nginx_path")

    cmd = _build_nginx_cmd(f'{nginx_bin} -t -c {config_path}')
    returncode, output = run_cmd_with_code(cmd)
    return returncode == 0, output


def reload_nginx():
    """
    重新加载Nginx配置（nginx -s reload）

    Returns:
        tuple: (是否成功, 输出信息)
    """
    nginx_bin = read_config("nginx", "nginx_bin_path")

    if _is_docker_mode():
        config_path = read_config("nginx", "nginx_container_path")
        cmd = _build_nginx_cmd(f'{nginx_bin} -s reload -c {config_path}')
    else:
        cmd = f'{nginx_bin} -s reload'
    returncode, output = run_cmd_with_code(cmd)

    if returncode == 0:
        time.sleep(0.5)

    return returncode == 0, output


def restart_nginx():
    """
    重启Nginx服务

    Returns:
        tuple: (是否成功, 输出信息)
    """
    if _is_docker_mode():
        container = _get_container_name()
        cmd = f'docker restart {container}'
        returncode, output = run_cmd_with_code(cmd, timeout=30)
        if returncode == 0:
            time.sleep(2)
            return True, output
        return False, f"Docker容器重启失败: {output}"

    try:
        nginx_bin = read_config("nginx", "nginx_bin_path")
        cmd = f'{nginx_bin} -s stop && {nginx_bin}'
    except Exception:
        cmd = "nginx -s stop && nginx"

    returncode, output = run_cmd_with_code(cmd, timeout=10)
    if returncode == 0:
        return True, output

    return False, f"Nginx重启失败，已尝试命令: {cmd}"


def _is_server_block_config(config_content):
    """判断配置内容是否包含 server 块"""
    for line in config_content.strip().split('\n'):
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            if re.match(r'^[\s]*server\s*\{', stripped):
                return True
    return False


def _find_http_block_end(content):
    """查找 http 块结束 } 的索引位置"""
    http_match = _find_block_range(content, 'http')
    if http_match is None:
        return None
    return http_match[1]


def _find_http_block_start(content):
    """查找 http { 之后的内容起始位置"""
    http_match = _find_block_range(content, 'http')
    if http_match is None:
        return None

    brace_pos = content.find('{', http_match[0])
    if brace_pos == -1:
        return None
    return brace_pos + 1


def _remove_test_config(content):
    """移除之前添加的测试配置"""
    pattern = r'\n?[^\S\n]*# ===== 自动化测试临时配置 =====\n.*?# ===== 自动化测试临时配置结束 =====\n?'
    return re.sub(pattern, '\n', content, flags=re.DOTALL)


def add_nginx_config(nginx_path, config_content):
    """
    向Nginx配置文件添加测试配置

    根据配置内容类型智能选择插入位置：
    - server 块：插入到 http 块开头（确保优先匹配）
    - location 块或其他指令：插入到最后一个 server 块内
    """
    path = Path(nginx_path)
    if not path.exists():
        raise FileNotFoundError(f"Nginx配置文件不存在: {nginx_path}")

    original_content = path.read_text(encoding='utf-8')
    original_content = _remove_test_config(original_content)

    is_server_block = _is_server_block_config(config_content)

    if is_server_block:
        http_block_start = _find_http_block_start(original_content)
        if http_block_start is None:
            raise Exception("Nginx配置文件格式错误：未找到http块")

        insert_index = http_block_start
        test_config = f"""

# ===== 自动化测试临时配置 =====
{config_content}
# ===== 自动化测试临时配置结束 =====
"""
    else:
        server_block_end = _find_last_server_block_end(original_content)

        if server_block_end is not None:
            insert_index = server_block_end
            indented_config = '\n'.join(
                '        ' + line if line.strip() else line
                for line in config_content.split('\n')
            )
            test_config = f"""

        # ===== 自动化测试临时配置 =====
{indented_config}
        # ===== 自动化测试临时配置结束 =====
"""
        else:
            http_block_end = _find_http_block_end(original_content)
            if http_block_end is None:
                raise Exception("Nginx配置文件格式错误：未找到http块")

            insert_index = http_block_end
            indented_config = '\n'.join(
                '        ' + line if line.strip() else line
                for line in config_content.split('\n')
            )
            test_config = f"""

    # ===== 自动化测试临时配置 =====
    server {{
        listen 80;
        server_name localhost;
{indented_config}
    }}
    # ===== 自动化测试临时配置结束 =====
"""

    new_content = original_content[:insert_index] + test_config + original_content[insert_index:]

    path.write_text(new_content, encoding='utf-8')

    logger.info(f"测试配置已添加至: {nginx_path}")
    logger.info(f"注入的测试配置内容:\n{config_content}")
    logger.info(f"注入后完整配置:\n{new_content}")
    return True


def _find_last_server_block_end(content):
    """查找 http 块内最后一个 server 块结束 } 的索引位置"""
    http_match = _find_block_range(content, 'http')
    if http_match is None:
        return None

    http_start, http_end = http_match
    http_content = content[http_start:http_end]

    server_match = _find_last_block_in_range(http_content, 'server')
    if server_match is None:
        return None

    return http_start + server_match[1]


def _find_block_range(content, block_name):
    """查找指定配置块的范围，返回 (开始位置, 结束}位置) 或 None"""
    pattern = re.compile(r'^[ \t]*' + block_name + r'\s*\{', re.MULTILINE)
    match = pattern.search(content)
    if not match:
        return None

    start = match.start()
    brace_start = match.end() - 1

    brace_count = 0
    pos = brace_start
    while pos < len(content):
        if content[pos] == '{':
            brace_count += 1
        elif content[pos] == '}':
            brace_count -= 1
            if brace_count == 0:
                return (start, pos)
        pos += 1

    return None


def _find_last_block_in_range(content, block_name):
    """在指定范围内查找最后一个配置块，返回 (开始位置, 结束}位置) 或 None"""
    pattern = re.compile(r'^[ \t]*' + block_name + r'\s*\{', re.MULTILINE)
    matches = list(pattern.finditer(content))

    if not matches:
        return None

    last_match = matches[-1]
    start = last_match.start()
    brace_start = last_match.end() - 1

    brace_count = 0
    pos = brace_start
    while pos < len(content):
        if content[pos] == '{':
            brace_count += 1
        elif content[pos] == '}':
            brace_count -= 1
            if brace_count == 0:
                return (start, pos)
        pos += 1

    return None


def read_nginx_error_log(lines=10):
    """读取Nginx错误日志最后N行"""
    try:
        error_log_path = read_config("nginx", "error_log_path")
    except Exception:
        return "无法读取error_log_path配置"

    path = Path(error_log_path)
    if not path.exists():
        return f"错误日志文件不存在: {error_log_path}"

    try:
        all_lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
        return '\n'.join(all_lines[-lines:])
    except Exception as e:
        return f"读取错误日志失败: {e}"


def get_nginx_version():
    """获取Nginx版本信息"""
    nginx_bin = read_config("nginx", "nginx_bin_path")
    cmd = _build_nginx_cmd(f'{nginx_bin} -v')
    try:
        return run_cmd(cmd)
    except Exception as e:
        return f"获取Nginx版本失败: {e}"
