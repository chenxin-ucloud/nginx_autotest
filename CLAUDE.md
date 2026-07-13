# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Nginx White-box Testing Automation Framework** (Nginx白盒测试自动化框架) that follows a data-script separation design. Test cases are defined in YAML files while test scripts handle execution logic only. Currently has **268 test cases** (262 in `test_data.yaml` + 6 gRPC), covering native nginx regression plus full functional/boundary testing of the `ngx_http_custom_rule_module`.

> **Platform: Linux.** Supports local Nginx and Docker-containerized OpenResty (`mode=local|docker`).

## Common Commands

### Run Tests

```bash
# Run all tests
pytest test_script/ -v

# Run non-gRPC cases only
pytest test_script/test_all.py -v

# Run specific test case by ID pattern
pytest test_script/test_all.py -v -k "add_header_001"

# Run with detailed traceback
pytest test_script/ -v --tb=long

# Generate HTML report
pytest test_script/ -v --html=reports/report.html
```

## Architecture Overview

### Data-Script Separation Design

The framework strictly separates test data from execution logic:

- **Test Data** (`test_data/*.yaml`): Contains test case ID, purpose, pre-conditions, Nginx config content, commands to execute, and expected/unexpected results.
- **Test Scripts** (`test_script/test_*.py`): Only contain execution logic. They read YAML data and use shared utilities.
- **Shared Utilities** (`comms/`): Provide reusable functions for Nginx operations, command execution, data reading, and logging.

### Key Modules

**`comms/` - Common Utilities**
- `nginx_operate.py`: Nginx operations (backup/restore config, check syntax, reload/restart, config injection, Docker adaptation via `_is_docker_mode`/`_build_nginx_cmd`/`run_nginx_cmd`)
- `cmd_operate.py`: Command execution wrappers (`run_cmd` raises on timeout, `run_cmd_with_code` returns code+output)
- `data_read.py`: YAML and INI config file parsers
- `constants.py`: Path constants and path helper functions
- `log_utils.py`: Logging singleton — writes to `logs/info.log` and `logs/error.log`, no console output
- `grpc_helper.py`: gRPC mock server lifecycle and client call helper for end-to-end gRPC tests

**`grpc_mock/` - gRPC Mock Server**
- `echo.proto`: Proto definition for Echo service
- `server.py`: Mock gRPC server that echoes received metadata
- `echo_pb2.py` / `echo_pb2_grpc.py`: Generated protobuf code

**`test_script/conftest.py`**
- Session-scoped fixture: backs up Nginx config before all tests, restores after completion
- Module-scoped fixture: restores Nginx config between test modules to ensure isolation

**`config/config.ini`**
- Central configuration for Nginx paths, ports, and report settings. All values must be present — no automatic fallback.

### Test Data Format

Non-gRPC cases live in `test_data/test_data.yaml` (single merged file). Three forms:

**Regular case — `operate_steps` (per-command independent assertion):**
```yaml
case_id_001:
  test_purpose: "描述测试目的"
  pre_condition:
    - "前置条件1"
  config_content: |
    multi_condition on;
    server {
      listen 18100;
      location /test { match_http_host www.test.com; return 200 "matched"; }
      location /catch_all { return 200 "no_match"; }
    }
  operate_steps:
    - command: 'curl -s -H "Host: www.test.com" http://127.0.0.1:18100/'
      expected:
        - "matched"
    - command: 'curl -s -H "Host: other.com" http://127.0.0.1:18100/'
      expected:
        - "no_match"
```
`nginx -t` / `nginx -s reload` are NOT placed in steps — the script runs `check_nginx_config()` + `reload_nginx()` itself; `test is successful` is verified implicitly by the syntax-check success. Each `command`'s `expected`/`unexpected` is asserted against **only that command's output**.

**Syntax-validation case — `expect_syntax_fail`:**
```yaml
case_id:
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
Script asserts `check_nginx_config()` fails and `expected_result` strings appear in the failure output.

**gRPC case** (in `test_data/grpc_set_header.yaml`) supports `grpc_verify` field for end-to-end metadata verification.

### Test Execution Flow

1. `conftest.py` session fixture backs up Nginx config
2. `conftest.py` module fixture restores config to clean state
3. Test script reads YAML data via `read_yaml()`
4. `pytest.mark.parametrize` iterates over all cases in YAML
5. For each case (`test_all.py::test_case`):
   - `add_nginx_config()` injects config content (logs the injected config + full config for troubleshooting)
   - `check_nginx_config()` runs `nginx -t`
   - If `expect_syntax_fail`: assert syntax check fails + `expected_result` in failure output, return
   - Otherwise: assert syntax check passes → `reload_nginx()` (fallback `restart_nginx()`)
   - If `operate_steps` present: for each step, `run_nginx_cmd(command)` then assert `expected` in this command's output and `unexpected` not in it
   - Else (legacy format): accumulate all command outputs, assert `expected_result` in combined output (fallback path)
6. Module fixture restores config after each module completes
7. Session fixture restores original config after all tests

### Logging

All test logging uses `comms.log_utils.logger` (not `print()`):
- `logs/info.log`: All INFO+ messages with timestamps, filenames, and line numbers
- `logs/error.log`: ERROR+ messages only
- Console: No output (StreamHandler removed)

Log format: `%(asctime)s - [%(filename)s - %(lineno)d] - %(levelname)s:%(message)s`

Import: `from comms.log_utils import logger`

## Important Implementation Details

### Path Management

Use constants from `comms.constants` instead of hardcoded paths:

```python
from comms.constants import DATA_DIR, get_test_data_path

test_data_path = get_test_data_path("test_data.yaml")  # Returns absolute path
```

### Adding New Test Cases

1. Append the new case (with a unique case ID) to `test_data/test_data.yaml` — all non-gRPC cases live in this single merged file, organized under section-header comments
2. For gRPC end-to-end cases that need the `grpc_verify` field, add them to `test_data/grpc_set_header.yaml` (the corresponding script `test_script/test_grpc_set_header.py` owns the module-scoped gRPC mock server fixture)
3. No new test script is needed for non-gRPC cases — `test_script/test_all.py` is a single parametrized function (`test_case`) that reads the merged YAML and supports three forms: `operate_steps` (per-command assertion), `expect_syntax_fail` (syntax must fail), and legacy `operate_commands` + flat `expected_result`/`unexpected_result` (combined-output fallback)
4. Prefer `operate_steps` for new regular cases — each command gets its own `expected`/`unexpected`, asserted against that command's output only
5. Import from `comms` package, not individual modules directly
6. Use `from comms.log_utils import logger` for all logging

### Nginx Config Injection

The `add_nginx_config()` function in `comms/nginx_operate.py` intelligently inserts test configurations:
- **server blocks**: Inserted at the start of the `http` block (for priority matching)
- **location blocks / other directives**: Inserted into the last `server` block

Configs are marked with comments for identification and cleanup:
```
# ===== 自动化测试临时配置 =====
{config_content}
# ===== 自动化测试临时配置结束 =====
```

The `_remove_test_config()` function cleans up previous test configs before injecting new ones.

### Configuration Requirements

`config/config.ini` — central configuration. All values must be present (no automatic fallback). Supports two modes:

**Local mode:**
```ini
[nginx]
mode = local
nginx_path = /etc/nginx/nginx.conf
nginx_bin_path = /usr/sbin/nginx
backup_path = /tmp/nginx_backup/
error_log_path = /var/log/nginx/error.log
```

**Docker mode** (config written on host via bind mount, commands run via `docker exec`):
```ini
[nginx]
mode = docker
container_name = alb-test
nginx_container_path = /ulb/global.conf
nginx_path = /ulb/alb-test/global.conf
nginx_bin_path = /usr/local/openresty/nginx/sbin/nginx
backup_path = /tmp/nginx_backup/
error_log_path = /ulb/alb-test/error.log
```
- `nginx_path`: host-side path for config read/write (bind-mounted into container)
- `nginx_container_path`: in-container path used as `-c` argument for `docker exec nginx` commands
- `run_nginx_cmd()` auto-wraps `nginx ...` commands with the binary path, `-c <container_path>`, and `docker exec <container>` in Docker mode

### Known Constraints

- HTTP/2 syntax depends on Nginx version: 1.25.1+ uses `http2 on;`, earlier versions (e.g. 1.20.1) must use `listen <port> http2;`. Test data targets OpenResty 1.27.1.2
- Test server blocks listening on port 80 should include both `listen 80;` and `listen [::]:80;` — on this host `localhost` resolves to `::1` first, and the system default server occupies `[::]:80`, so an IPv4-only injected block will never match
- Test `proxy_pass` targets must point to a non-listening port (e.g. `127.0.0.1:19999`) rather than `127.0.0.1:80`, otherwise the request loops back into Nginx and the curl command times out
- The framework adds `time.sleep(0.5)` after reload to allow Nginx to finish re-reading config
- gRPC mock server binds to `0.0.0.0` (not `[::]`) for IPv4 compatibility
- The `_remove_test_config` regex uses `[^\S\n]*` (not `\s*`) to avoid consuming newlines that break brace matching
- Tests require write permission to Nginx config files and the backup directory
- **Stale backups**: after switching modes or manual probing, `/tmp/nginx_backup/` may contain a backup with `multi_condition on;` from a previous run. The module fixture `restore_nginx_config()` picks the latest backup, causing subsequent cases to report `"multi_condition" directive is duplicate`. Clean before running: `rm -f /tmp/nginx_backup/nginx_backup_*.conf`
- **Docker PID file**: in Docker mode, `nginx -s reload/stop` must include `-c /ulb/global.conf` so nginx finds the correct PID file (the container uses `pid /ulb/nginx.pid;`, not the OpenResty default). `run_nginx_cmd()` and `reload_nginx()` handle this automatically
- **Docker restart**: the container runs `daemon off;` with nginx as PID 1, so `nginx -s stop` would kill the container. `restart_nginx()` uses `docker restart` instead in Docker mode
- **curl HEAD**: use `curl -I` not `curl -X HEAD` — the latter hangs waiting for a body that never arrives
- **Config injection of mixed content**: `_is_server_block_config()` scans all lines (not just the first) so `multi_condition on;` + `server {}` content is correctly detected as a server block and injected at the `http {` start, keeping `multi_condition` at http scope
- **Custom rule module** (`ngx_http_custom_rule_module`): `multi_condition on` replaces native server_name/location matching with custom multi-condition matching (top-to-bottom, first match wins). Directives: `match_http_host/path/header/cookie/request_method/source_ip/query_string`, `response_rule`, `match_http_status`, `match_response_http_header`, `response_add/delete_http_header`, `delete_http_header`. Variables: `$custom_rule_request_rule_name`, `$custom_rule_response_rule_name`
