# 对照模块测试说明（gb-0045）

三个测试层级，均在本地 Python3.11 运行（依赖：fastapi/uvicorn/SQLAlchemy/PyJWT/numpy/redis/scipy，scipy 仅作 oracle）：

## 1. 求解器 oracle：`oracle_bounds.py`

自研最小费用流（SSP） vs `scipy.optimize.linprog`（HiGHS）：

- 400 个随机运输多面体实例（2–5 年龄段 × 2–4 来访方式、随机占比归一、随机不可能组合、代价含无配对组 ±16）。
- 可行实例：上下界与 oracle 误差 < 1e-6；达到构成满足边际占比、禁用组合为零、目标值等于界。
- 不可行实例：Hall 证据成立（可达行集合占比合计 > 其可行列合计，且无可达行到非可达列的允许边）。

## 2. 服务单元：`test_compare_service.py`

41 项：配对键（访客/展品/实际星级）、单侧多余记录计数、分组差值、2×2 手算上下界与达到构成、
无配对组 ±16 计入、区间含零不判胜负、全正/全负判定、四类冲突（合计不为1/两侧不等/整行禁用/Hall 缺口）、
禁用组合不进入构成、版本输入校验、受理时锁定同版数据（SQLite 内存库：旧对照保持 v1 快照、新对照采用 v2）。

## 3. HTTP 全流程：`test_http.py`

uvicorn + SQLite（端口 19299，自动启停；本地无 Redis，种子任务用 `worker.execute` 直接计算）：

- 种子 → 两份研究完成 → 发起对照 → 结论/界/达到构成/采用版本字段齐全（配对 40 条留出记录）。
- 并发：8 线程更新客群版本 + 8 线程发起对照，逐份核对 `profile_snapshot` 与所锁版本 payload 完全一致。
- 冲突版本（两侧合计不等）→ 对照结论 `infeasible` 且报告冲突类型与说明。
- 权限与校验：viewer 写操作 403、匿名 401、同研究 422、研究不存在 404、负占比 422、对照不存在 404。

运行：

```bash
python3 oracle_bounds.py
python3 test_compare_service.py
python3 test_http.py
```
