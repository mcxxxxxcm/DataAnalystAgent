# Change Recipe：持久化 Effects 队列 + 指数退避（执行剧本）

## Step 1 —— 读约定
- **Context**: 本 change 落 `utils` + `core/database` + `config`；涉及执行重试，注意不吞错、不改安全边界。
- **Action**: 读 `openspec/agreement.md`；确认不退安全红线、声明 timeout 真正生效（Avoid §5）。
- **Validation**: 已确认属重试基建增强、不放松安全。 `[ ]`

## Step 2 —— 写 `AsyncEffectQueue`
- **Context**: 复现 dsh Effects 的 key 幂等 + 指数退避 + 持久化句型。
- **Action**: 新建 `utils/effect_queue.py`：`_Effect`、`AsyncEffectQueue.enqueue(kind,key,fn,...)`（同 key 未 settle 则替换并立即到期）、`process()`（到期任务顺序执行，瞬时失败按 `base_delay*2^attempts+jitter` 重排，超 `max_attempts` 失败）、`pending()/settled()/failed()/sweep()`、JSONL 持久化 `_persist`/`_restore`（当 `persist_path` 给定）。
- **Validation**: `tests/test_effect_queue.py` 中 key 合并/退避/超限/持久用例通过。 `[ ]`

## Step 3 —— 配置项
- **Context**: 退避参数可配且给默认值。
- **Action**: `config/settings.py` 新增 `effect_queue_max_retries=2(ge=0)`、`effect_queue_base_delay=1.0`、`effect_queue_persist=False`、`effect_queue_persist_path: Optional[str]=None`；`persist_path` 为 None 且 persist 时用 `logs/effect_queue.jsonl`。
- **Validation**: `py -m pytest tests/test_settings_defaults.py -q` 通过；新属性返回默认。 `[ ]`

## Step 4 —— 接通 SQL 瞬时路径
- **Context**: 让队列有真实消费者（避免「为假设造库」），但作为补充层不破坏 ToolRetryMiddleware。
- **Action**: 在 `core/database/pool.py` 提供 `run_sql_durable(fn)`：若 `effect_queue_max_retries>0` 且 `is_transient_error(exc)`，把重试封装进 `AsyncEffectQueue`（key=规范化 SQL 哈希）并 `await process()`；若结果为最终失败仍抛原始异常。在瞬时异常分支调用，`effect_queue_max_retries==0` 时完全跳过维持现状。
- **Validation**: 现有 `tests/test_sql_error.py`/`test_sql_tools.py` 保持通过；无回归。 `[ ]`

## Step 5 —— 测试
- **Context**: 测试是硬门槛。
- **Action**: 新增 `tests/test_effect_queue.py`（key 幂等、退避递增、max_attempts 失败、JSONL 恢复、pending/settled、瞬时判定）；`py -m pytest tests/ -q`。
- **Validation**: 全绿（基线 138 + 新增）。 `[ ]`

## Final —— 收尾自检
- overview How 逐条兑现；更新 `README.md`/`CHANGELOG.md`（新增重试退避能力）；本 change 目录移至 `openspec/archived/`。 `[ ]`