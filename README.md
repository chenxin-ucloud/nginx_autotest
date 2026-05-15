# Nginx 白盒测试自动化框架

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![pytest](https://img.shields.io/badge/pytest-7.0+-blue.svg)](https://pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

一款基于 Python + pytest 的 Nginx 白盒测试自动化框架，采用数据与脚本分离的设计理念。

> **平台：Linux。** Nginx 应通过包管理器（apt/yum）安装或从源码编译安装。

## 特性

- **数据-脚本分离**：测试用例使用 YAML 定义，测试逻辑使用 Python 实现
- **配置智能注入**：自动将测试配置注入 Nginx 配置文件，支持 server 块和 location 块的智能插入
- **测试隔离**：每个测试模块自动备份和恢复 Nginx 配置
- **gRPC 端到端测试**：内置 gRPC mock 服务器，支持 grpc_set_header 等指令的功能验证
- **日志系统**：统一的日志模块，输出到 `logs/` 目录，不干扰终端显示
- **优先级验证**：支持 `unexpected_result` 反向断言，验证匹配优先级

## 目录结构

```
nginx_autotest/
├── comms/                    # 公共工具模块
│   ├── cmd_operate.py       # 命令执行封装
│   ├── constants.py         # 路径常量
│   ├── data_read.py         # YAML/INI 配置读取
│   ├── grpc_helper.py       # gRPC 服务启停与客户端调用
│   ├── log_utils.py         # 日志模块（文件输出）
│   └── nginx_operate.py     # Nginx 操作（备份/恢复/重载/配置注入）
├── config/
│   └── config.ini           # Nginx 路径配置
├── grpc_mock/               # gRPC Mock 服务
│   ├── echo.proto           # Proto 定义
│   ├── server.py            # Mock 服务端
│   ├── client.py            # 测试客户端
│   ├── echo_pb2.py          # 生成的 protobuf 代码
│   └── echo_pb2_grpc.py     # 生成的 gRPC 代码
├── logs/                    # 日志输出目录
│   ├── info.log             # INFO 级别日志
│   └── error.log            # ERROR 级别日志
├── test_data/               # 测试数据（YAML）
│   ├── add_header.yaml      # 添加响应头（1 条）
│   ├── grpc_set_header.yaml # gRPC 请求头设置（6 条）
│   ├── location.yaml        # location 匹配规则及优先级（10 条）
│   ├── proxy_hide_header.yaml # 隐藏代理响应头（1 条）
│   ├── proxy_pass_header.yaml # 代理响应头传递（1 条）
│   ├── proxy_set_header.yaml  # 设置代理请求头（2 条）
│   └── server_name.yaml    # server_name 匹配及优先级（8 条）
├── test_script/             # 测试脚本
│   ├── conftest.py          # pytest 全局/模块级夹具
│   ├── test_add_header.py
│   ├── test_grpc_set_header.py
│   ├── test_location.py
│   ├── test_proxy_hide_header.py
│   ├── test_proxy_pass_header.py
│   ├── test_proxy_set_header.py
│   └── test_server_name.py
├── CLAUDE.md                # Claude Code 项目指引
└── README.md                # 本文件
```

## 快速开始

### 环境要求

- Python 3.8+
- Nginx 1.25.1+（推荐 1.30.0，使用 `http2 on;` 语法）
- curl 命令行工具
- grpcio（仅 gRPC 测试需要）

### 安装依赖

```bash
pip install pytest pyyaml grpcio grpcio-tools
```

### 配置 Nginx 路径

编辑 `config/config.ini`，配置 Nginx 路径：

```ini
[nginx]
nginx_path = /etc/nginx/nginx.conf
nginx_bin_path = /usr/sbin/nginx
backup_path = /tmp/nginx_backup/
error_log_path = /var/log/nginx/error.log
```

### 运行测试

```bash
# 运行全部 29 条测试用例
pytest test_script/ -v

# 运行特定测试模块
pytest test_script/test_location.py -v

# 运行特定测试用例
pytest test_script/test_add_header.py -v -k "add_header_001"

# 生成 HTML 测试报告
pytest test_script/ -v --html=reports/report.html
```

## 测试数据格式

测试用例使用 YAML 格式定义：

```yaml
case_id_001:
  test_purpose: "验证基础功能-添加自定义响应头"
  pre_condition:
    - Nginx配置文件路径已知
    - 已备份原始配置文件
  config_content: |
    location /test {
      add_header X-Custom "value";
      return 200 "OK";
    }
  operate_commands:
    - "nginx -t"
    - "nginx -s reload"
    - "curl -v http://localhost/test"
  expected_result:
    - "test is successful"
    - "X-Custom: value"
  unexpected_result:          # 可选，反向断言
    - "should not appear"
```

gRPC 端到端测试还支持 `grpc_verify` 字段：

```yaml
grpc_set_header_001:
  # ... 基本字段 ...
  grpc_verify:
    target: "localhost:19080"
    message: "test"
    expect_metadata:
      x-custom-header: "injected_by_nginx"
    client_metadata:          # 可选，客户端携带的 metadata
      x-client-id: "original"
```

## 支持的测试模块

| 模块 | 描述 | 用例数 | 测试文件 |
|------|------|--------|----------|
| add_header | 添加响应头 | 1 | `test_add_header.py` |
| grpc_set_header | gRPC 请求头设置（含端到端验证） | 6 | `test_grpc_set_header.py` |
| location | location 匹配规则及优先级（= > ^~ > ~* > 前缀 > /） | 10 | `test_location.py` |
| proxy_hide_header | 隐藏代理响应头 | 1 | `test_proxy_hide_header.py` |
| proxy_pass_header | 代理响应头传递 | 1 | `test_proxy_pass_header.py` |
| proxy_set_header | 设置代理请求头 | 2 | `test_proxy_set_header.py` |
| server_name | server_name 匹配及优先级（精确 > 前缀通配 > 后缀通配 > 正则 > default） | 8 | `test_server_name.py` |

## 日志系统

框架使用统一的日志模块 `comms/log_utils.py`，替代所有 `print()` 输出：

- **INFO 日志** → `logs/info.log`：记录测试步骤、执行结果
- **ERROR 日志** → `logs/error.log`：记录断言失败、异常信息
- **终端**：不输出日志，保持 pytest 输出整洁

日志格式示例：
```
2026-05-14 23:25:05,626 - [test_add_header.py - 44] - INFO:开始执行 [add_header_001] 验证基础功能-添加自定义响应头
2026-05-14 23:25:06,959 - [test_add_header.py - 93] - INFO:[add_header_001] 验证基础功能-添加自定义响应头 执行成功！
```

## 添加新测试模块

1. 在 `test_data/` 目录创建 YAML 测试数据文件
2. 在 `test_script/` 目录创建对应的测试脚本（复制现有脚本，修改 YAML 文件名）
3. 使用 `from comms.log_utils import logger` 记录日志
4. 支持 `unexpected_result` 字段做反向断言
5. gRPC 类测试可参考 `test_grpc_set_header.py` 的 fixture 和 `grpc_verify` 模式

## 注意事项

1. **端口冲突**：确保测试使用的端口（80、18090、19080、19090）未被占用
2. **配置备份**：框架会自动备份和恢复 Nginx 配置，但建议手动备份重要配置
3. **Nginx 版本**：推荐 1.25.1+，HTTP/2 需使用 `http2 on;` 指令而非 `listen ... http2`
4. **日志查看**：测试运行后查看 `logs/info.log` 获取详细执行日志
5. **权限要求**：测试需要对 Nginx 配置文件和备份目录的写入权限，建议使用 sudo 或配置适当的文件权限

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
