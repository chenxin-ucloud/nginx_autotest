# Nginx 白盒测试自动化框架

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![pytest](https://img.shields.io/badge/pytest-7.0+-blue.svg)](https://pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

一款基于 Python + pytest 的 Nginx 白盒测试自动化框架，采用数据与脚本分离的设计理念，支持本地与 Docker 容器两种 Nginx 部署模式，覆盖 `ngx_http_custom_rule_module` 自定义规则模块的全量功能与边界测试。

> **平台：Linux。** Nginx 可通过包管理器安装或从源码编译；亦支持 Docker 容器内运行的 OpenResty。

## 特性

- **数据-脚本分离**：测试用例使用 YAML 定义，测试逻辑使用 Python 实现
- **每命令独立断言**：`operate_steps` 结构让每条命令对应自己的 expected/unexpected，仅对该命令输出断言，避免合并输出导致的误判
- **配置智能注入**：自动将测试配置注入 Nginx 配置文件，支持 server 块和 location 块的智能插入
- **双模式**：支持本地 Nginx 与 Docker 容器内 Nginx（`mode=local|docker`），Docker 模式下命令经 `docker exec` 执行、配置经宿主机挂载卷读写
- **测试隔离**：session 级备份/恢复 Nginx 配置，模块级恢复保证隔离
- **gRPC 端到端测试**：内置 gRPC mock 服务器，支持 grpc_set_header 等指令的功能验证
- **语法校验**：`expect_syntax_fail` 字段断言配置语法检查必须失败并验证错误串
- **日志系统**：统一日志模块输出到 `logs/`，注入配置与完整配置均记录便于排查

## 目录结构

```
nginx_autotest/
├── comms/                    # 公共工具模块
│   ├── cmd_operate.py       # 命令执行封装（run_cmd/run_cmd_with_code）
│   ├── constants.py         # 路径常量
│   ├── data_read.py         # YAML/INI 配置读取
│   ├── grpc_helper.py       # gRPC 服务启停与客户端调用
│   ├── log_utils.py         # 日志模块（文件输出）
│   └── nginx_operate.py     # Nginx 操作（备份/恢复/重载/配置注入/Docker 适配）
├── config/
│   └── config.ini           # Nginx 路径与模式配置
├── grpc_mock/               # gRPC Mock 服务
├── test_data/               # 测试数据（YAML）
│   ├── test_data.yaml       # 全部非 gRPC 用例（262 条：回归 + 自定义规则模块全量）
│   └── grpc_set_header.yaml # gRPC 用例（6 条，需 mock server）
├── test_script/             # 测试脚本
│   ├── conftest.py          # pytest session/模块级夹具
│   ├── test_all.py          # 全部非 gRPC 用例（每命令独立断言 + 旧格式回退）
│   └── test_grpc_set_header.py  # gRPC 用例（含模块级 mock server fixture）
├── CLAUDE.md                # Claude Code 项目指引
└── README.md                # 本文件
```

## 快速开始

### 环境要求

- Python 3.8+
- Nginx 或 Docker（OpenResty）——本框架已在 `hub.ucloudadmin.com/iaas/wafulb:3.0`（OpenResty 1.27.1.2 + `ngx_http_custom_rule_module`）上验证
- curl 命令行工具
- grpcio / grpcio-tools（仅 gRPC 测试需要）

### 安装依赖

```bash
pip install pytest pyyaml grpcio grpcio-tools
```

### 配置 Nginx 路径

编辑 `config/config.ini`。**本地模式**：

```ini
[nginx]
mode = local
nginx_path = /etc/nginx/nginx.conf
nginx_bin_path = /usr/sbin/nginx
backup_path = /tmp/nginx_backup/
error_log_path = /var/log/nginx/error.log
```

**Docker 模式**（容器内 Nginx，配置经宿主机挂载卷读写，命令经 `docker exec` 执行）：

```ini
[nginx]
mode = docker
container_name = alb-test
nginx_container_path = /ulb/global.conf      # 容器内路径（-c 参数）
nginx_path = /ulb/alb-test/global.conf        # 宿主机挂载卷路径（读写配置）
nginx_bin_path = /usr/local/openresty/nginx/sbin/nginx
backup_path = /tmp/nginx_backup/
error_log_path = /ulb/alb-test/error.log
```

### 运行测试

```bash
# 运行全部 268 条用例
pytest test_script/ -v

# 仅运行非 gRPC 用例
pytest test_script/test_all.py -v

# 按用例 ID 筛选
pytest test_script/test_all.py -v -k "match_host_001"

# 生成 HTML 报告
pytest test_script/ -v --html=reports/report.html
```

## 测试数据格式

### 常规用例（operate_steps，每命令独立断言）

```yaml
case_id_001:
  test_purpose: "验证基础功能"
  pre_condition:
    - Nginx配置文件路径已知
  config_content: |
    multi_condition on;
    server {
      listen 18100;
      location /test { match_http_host www.test.com; return 200 "matched"; }
      location /catch_all { return 200 "no_match"; }
    }
  operate_steps:
    - command: "curl -s -H \"Host: www.test.com\" http://127.0.0.1:18100/"
      expected:
        - "matched"
    - command: "curl -s -H \"Host: other.com\" http://127.0.0.1:18100/"
      expected:
        - "no_match"
```

说明：`nginx -t` / `nginx -s reload` 不再放入 steps——脚本通过 `check_nginx_config()` / `reload_nginx()` 处理；每条 `command` 的 `expected` 仅对该命令输出断言，`unexpected` 断言不应出现。

### 语法校验用例（expect_syntax_fail）

```yaml
case_id:
  test_purpose: "验证重复配置报错"
  config_content: |
    multi_condition on;
    server { listen 18100; location /a { match_http_host a.com; match_http_host b.com; } }
  operate_commands:
    - "nginx -t"
  expect_syntax_fail: true
  expected_result:
    - "is duplicate"
    - "test failed"
```

### gRPC 用例（grpc_verify）

```yaml
grpc_set_header_001:
  config_content: |
    server { listen 19080; http2 on; location / { grpc_pass grpc://127.0.0.1:19090; grpc_set_header X-Grpc-Test "grpc_value"; } }
  operate_commands:
    - "nginx -t"
    - "nginx -s reload"
  expected_result:
    - "test is successful"
  grpc_verify:
    target: "127.0.0.1:19080"
    message: "test"
    expect_metadata:
      x-grpc-test: "grpc_value"
```

## 测试覆盖（262 + 6 = 268 条）

| 类别 | 用例数 | 说明 |
|------|--------|------|
| 回归（add_header/location/server_name/proxy_*） | 24 | 原生 nginx 指令功能与匹配优先级 |
| multi_condition 开关 | 2 | on/off 与原生匹配切换 |
| match_* 单关键字匹配 | 33 | host/path/header/cookie/method/source_ip/query 各匹配类型 |
| match_* 在 response_rule 对应 | 39 | 7 种请求关键字在 response_rule 上下文一一对应 |
| 大小写敏感 | 15 | host/header/cookie/qs/response_header 精确与正则 `~`/`~*` |
| keyval 正则key/重复key | 11 | 正则匹配 key、同 key 不同 value AND |
| 匹配不中/默认/优先级/回退 | 14 | 不中回退兜底、无条件匹配所有、命中第一个 |
| 组合条件 | 3 | 全条件 AND、部分不中、变量 |
| response_rule 高级/响应头交叉 | 26 | match_response_http_header、always/safe_status、变量、rewrite、响应头增删 8 组合 |
| always/safe_status | 2 | safe 状态码全覆盖（10 个）+ 非 safe 不带 always 不添加 |
| 变量/转发日志 | 4 | $custom_rule_request/response_rule_name、proxy_set_header 转发、access_log |
| IPv6/URL编码边界 | 2 | IPv6 ::1/::0、URL 编码 query 解码 |
| 规模交叉组合 | 2 | 50 条规则规模、单值多值+5 种 path 类型+9 条件交叉 |
| 语法校验/边界 | 78 | 重复/无参数/非枚举/非法 IP/掩码/正则/上下文/内置头保护等 |
| gRPC | 6 | grpc_set_header 端到端 |

## 日志系统

- **INFO 日志** → `logs/info.log`：测试步骤、执行结果；`add_nginx_config()` 记录注入的测试配置与完整配置
- **ERROR 日志** → `logs/error.log`：断言失败、异常信息
- **终端**：不输出日志，保持 pytest 输出整洁

## 添加新测试用例

1. 在 `test_data/test_data.yaml` 追加用例（gRPC 用例加入 `grpc_set_header.yaml`）
2. **常规用例**用 `operate_steps`（每命令独立 expected/unexpected）；**语法校验用例**用 `expect_syntax_fail: true` + `expected_result`
3. `nginx -t` / `nginx -s reload` 不必放入 steps（脚本自动处理）
4. 用 `from comms.log_utils import logger` 记录日志

## 注意事项

1. **端口冲突**：测试使用 80、18080-18101、19080、19090 端口，确保未被占用
2. **stale 备份**：切换模式或手动探测后，`/tmp/nginx_backup/` 可能残留含 `multi_condition` 的备份导致后续用例报 "directive is duplicate"，运行前清理：`rm -f /tmp/nginx_backup/nginx_backup_*.conf`
3. **Docker 模式**：容器用 `daemon off;` 且 nginx 为 PID 1，`nginx -s stop` 会杀容器，故 `restart_nginx()` 用 `docker restart`；reload/stop 需带 `-c /ulb/global.conf` 指定 PID 文件
4. **配置注入**：`add_nginx_config()` 对含 `multi_condition on;` + `server {}` 的混合内容按 server 块处理，注入到 `http {` 之后
5. **proxy_pass 目标**：`proxy_pass` 不要指向本机 Nginx 监听端口，使用未监听端口避免自循环
6. **curl HEAD**：用 `curl -I` 而非 `curl -X HEAD`（后者会挂起）
7. **日志查看**：测试运行后查看 `logs/info.log` 获取详细执行日志与注入配置

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
