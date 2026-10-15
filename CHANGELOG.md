# Changelog

## v0.1.0 — 个人版首发（开源化冲刺）

> 单机 SQLite 个人版首发。范围见 `项目开源需求大纲.md` / REQ-2026-002。

### 安全 / 凭据
- **OSS-02 密码修改功能**：新增 `POST /api/auth/change-password`；用户登录后可自行改密。
- **旧 token 吊销**：Member 新增 `token_valid_from`，改密后所有更早签发的 JWT 立即失效（无状态吊销，零开销）。
  - *修复（2026-10-14，全面测试中发现）*：吊销判断在 SQLite 下因 naive datetime 时区错位（约 8h）与亚秒精度误判，会导致旧 token 不吊销或新 token 被误吊销；已改为 UTC 归一 + 整数秒比较（`server/app/api/deps.py`）。
- **移除全部硬编码口令字面量**：源码、脚本、测试、文档不再出现默认口令。
- **首启随机口令**：新库首次启动由系统生成一次性随机密码并打印到控制台（账号 `admin`），登录后请立即修改。
- **JWT 密钥首启自生成**：仍为占位默认值时，随机生成并写入 `pm-collab/.env`（已被 `.gitignore` 排除），控制台提示一次。
- 默认监听 `127.0.0.1`；AI 接入使用与人类一致的账号密码。

### 数据库升级（OSS-01）
- `db_bootstrap` 幂等 ALTER 补齐 `members.token_valid_from` 等列；老库升级数据完整保留，无需导出导入。

### 仓库与发布（OSS-03 / OSS-04 / OSS-05）
- 选定 **MIT** 许可证（仓库根 `LICENSE`）。
- 第三方依赖许可清单见 `docs/third-party-licenses.md`（默认依赖均为宽松许可，无 GPL/AGPL 传染）。
- 根目录文档归档至 `docs/`（design / user-guide / testing），`.gitignore` 补全。
- README 含 5 分钟快速上手；Issue 欢迎（模板 v0.2 补）。

### 工程（OSS-06）
- GitHub Actions CI：Python pytest + 前端 web build 双绿。
