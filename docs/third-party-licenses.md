# 第三方依赖许可清单（Third-party Licenses）

> 由 `pip-licenses` / `license-checker` 生成并人工核对。OSS-03 要求：默认依赖均为宽松许可，无 GPL/AGPL 传染。
> 生成方式：`pip install pip-licenses && pip-licenses --format=markdown --output-file=../docs/third-party-licenses.md`（于 `pm-collab/` 下执行）。

## Python（默认安装，SQLite 单机形态）

| 包 | 版本 | 许可证 |
| --- | --- | --- |
| fastapi | 0.115.6 | MIT |
| uvicorn[standard] | 0.34.0 | BSD-3-Clause |
| sqlalchemy | 2.0.36 | MIT |
| alembic | 1.14.0 | MIT |
| pydantic | 2.10.5 | MIT |
| pydantic-settings | 2.7.1 | MIT |
| PyJWT | 2.10.1 | MIT |
| bcrypt | 4.2.1 | Apache-2.0 |
| watchdog | 6.0.0 | Apache-2.0 |
| APScheduler | 3.10.4 | MIT |
| python-multipart | 0.0.20 | MIT |
| pytest | 8.3.4 | MIT |
| pytest-cov | 6.0.0 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |

### 可选（仅启用 PostgreSQL 时安装，不参与默认发行）
| 包 | 版本 | 许可证 | 说明 |
| --- | --- | --- | --- |
| psycopg[binary] | 3.2.3 | LGPL-3.0 | 仅 PG 形态需要；SQLite 默认形态不安装，故不触发 copyleft 传染。 |

## 前端（npm）

| 包 | 版本 | 许可证 |
| --- | --- | --- |
| vue | ^3.5.13 | MIT |
| vue-router | ^4.5.0 | MIT |
| element-plus | ^2.9.1 | MIT |
| axios | ^1.7.9 | MIT |
| echarts | ^5.5.1 | Apache-2.0 |
| vite | ^6.0.5 | MIT |
| @vitejs/plugin-vue | ^5.2.1 | MIT |

## 结论
默认依赖（Python + 前端）全部为 MIT / BSD / Apache-2.0 宽松许可，无 GPL/AGPL。可选依赖 `psycopg` 为 LGPL-3.0，仅在显式启用 PostgreSQL 时安装，不在默认发布物内。
