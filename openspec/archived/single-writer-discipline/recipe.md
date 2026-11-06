# Change Recipe：单一写者纪律审计（执行剧本）

## Step 1 —— 读约定
- **Context**: 对齐项目宪法，本 change 落 `utils` 层，属重构（不改安全边界）。
- **Action**: 读 `openspec/agreement.md`，确认不触碰安全红线；复用而非重复（Avoid §4）。
- **Validation**: 已确认属 `utils` 层重构、不新增危险能力。 `[ ]`

## Step 2 —— 写 `BoundedTTLCache` 原语
- **Context**: 单一写者缓存原语，替代两处重复实现。
- **Action**: 新建 `utils/bounded_cache.py`：`BoundedTTLCache(max_entries, ttl_seconds)`，实现 `set`/`get`(只读，过期惰性回收)/`pop`(一次性删除)/`size`/`clear`；注释说明单事件循环无真争用。
- **Validation**: `py -m pytest tests/test_bounded_cache.py -q` 通过（见 Step 5）。 `[ ]`

## Step 3 —— 收敛 `result_store`
- **Context**: 消除重复，保持对外签名不变。
- **Action**: 修改 `utils/result_store.py`：用类级 `_cache = BoundedTTLCache(max_entries=50, ttl_seconds=600)` 替换 `_store/_expiry`；`set_result/get_result/clear/cache_size` 委托其上。
- **Validation**: `get` 读后条目仍在（非摧毁）；`cache_size` 正确。 `[ ]`

## Step 4 —— 收敛图表 spec 缓存并修正摧毁式读
- **Context**: `get_cached_spec` 用 `.pop()` 摧毁式读，违反读不写。
- **Action**: 修改 `tools/chart_tools.py`：`_spec_cache = BoundedTTLCache(...)`；`get_cached_spec` 改为 `_spec_cache.get(chart_id)`（只读）；`_store_spec` 改用 `.set`。检查 `create_custom_chart` 与 `/chart/option` 读路径无一次消费依赖（保持只读 `get`）。
- **Validation**: `tests/test_single_writer.py` 断言读后条目仍在、读不改变 size；`/chart/option` 语义不变。 `[ ]`

## Step 5 —— 文档与单测
- **Context**: 单一写者约定需要被记录并兜底。
- **Action**: 新建 `docs/state-owners.md`（各状态唯一写者表）；`openspec/design.md` 加指针；新增 `tests/test_bounded_cache.py` 与 `tests/test_single_writer.py`。
- **Validation**: `py -m pytest tests/ -q` 全绿（基线 138 + 新增）。 `[ ]`

## Final —— 收尾自检
- overview How 逐条兑现；更新 `CHANGELOG.md`（如读路径行为更健壮，属可记录变更）；本 change 目录移至 `openspec/archived/`。 `[ ]`