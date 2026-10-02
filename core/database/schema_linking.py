"""
Schema Linking —— 相关表加权评分检索

位置：core/database/schema_linking.py
职责：把「用户查询」与「库内表」做分词/关键词/同义/长度归一打分，
返回按相关性降序的 Top-K 表(含命中理由)。替代原先 schema.py 里的硬编码
KEYWORD_TABLE_MAP + 表名 Contains 匹配。

设计目标(借鉴 Vanna / DB-GPT / WrenAI 的 schema linking 思路)：
- 零新依赖：纯文本加权打分，不引入向量库/embedding。
- 可解释：每表返回 reasons([])，供 LLM 决策与 HITL 轨迹复用。
- 兜底：无命中时回退到近期使用过的表或配置优先级表，并标记 fallback。

纯逻辑模块，不触库；所有输入(表名/列名/注释)由调用方(SchemaManager)注入，
便于脱离数据库单测。
"""

from typing import Dict, List, Tuple, Optional
import re

# 业务同义词表(中/英)。词的 token 命中任一对应物即对映射目标表加分。
# 仅作初始覆盖；用户可用 settings.schema_synonyms 追加。
DEFAULT_SYNONYMS: Dict[str, List[str]] = {
    '销售': ['sales', 'sale', 'revenue', '收入', '成交', '业绩'],
    '订单': ['orders', 'order', 'order_items', '下单', '购买'],
    '用户': ['users', 'user', 'customer', '客户', '会员'],
    '产品': ['products', 'product', '商品', 'sku', 'item'],
    '收入': ['sales', 'revenue', '收入', '成交额'],
    '利润': ['profit', 'margin', '利润'],
    '退款': ['refund', 'returns', '退货', '退款'],
    '库存': ['inventory', 'stock', '库存'],
}

def build_synonym_map(user_map: Optional[Dict[str, List[str]]] = None) -> Dict[str, List[str]]:
    """合并业务默认同义词与用户自定义同义词（用户覆盖默认）。"""
    merged: Dict[str, List[str]] = {
        word: list(targets)
        for word, targets in DEFAULT_SYNONYMS.items()
    }
    for word, targets in (user_map or {}).items():
        merged[word] = [t.lower() for t in targets]
    return merged


# slug 化后较短且罕见的标点/停用词，避免把整表列名当噪音。
_STOP_CHARS = re.compile(r"[，。、；：！？（）\[\]{}%\s\t,.;:\"'`|/\\-]+")


def _tokenize(text: str) -> List[str]:
    """简单分词：英文按单词，中文按字序列(长句整体)，返回小写清理后的 token 集。"""
    text = text or ""
    text_lower = text.lower()
    # 保留中文短语(用非中英数字分隔)
    parts = re.split(r"[^0-9a-z一-鿿]+", text_lower)
    tokens: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if re.fullmatch(r"[0-9a-z_]{2,}", p):
            tokens.append(p)
        elif re.search(r"[一-鿿]", p):
            # 中文：整段作为一个潜在匹配单位，同时拆出 2+ 字实词
            tokens.append(p)
    return tokens


def _norm(table_name: str) -> str:
    """单复数/下划线归一：users->user，order_items->order item。"""
    t = table_name.lower().replace('_', ' ')
    if t.endswith('s') and not t.endswith('ss'):
        t = t[:-1]
    return t


class ScoredTable:
    """带分数的候选表。"""

    def __init__(self, table: str, score: float, reasons: List[str]):
        self.table = table
        self.score = score
        self.reasons = reasons


class TableIndex:
    """
    表检索索引。

    由 SchemaManager 构建：为每张表缓存 表名形态 / 列名集 / 列注释 / 表注释 /
    同义词。build 惰性，避免启动时全量触库。
    """

    def __init__(self) -> None:
        # table -> 命中线索
        self._tables: List[Dict] = []
        self._ready = False

    def reset(self) -> None:
        self._tables.clear()
        self._ready = False

    def add(
        self,
        table: str,
        columns: Optional[List[Dict]] = None,
        table_comment: Optional[str] = None,
        synonyms: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        cols = columns or []
        self._tables.append({
            'table': table,
            'norm': _norm(table),
            'name_tokens': _tokenize(table),
            'column_tokens': _tokenize(' '.join(c.get('name', '') for c in cols)),
            'column_comments': _tokenize(' '.join(str(c.get('comment', '') or '') for c in cols)),
            'table_comment': _tokenize(table_comment or ''),
            'synonyms': synonyms or {},
        })
        self._ready = True


def score_table(query_tokens: List[str], entry: Dict) -> Tuple[float, List[str]]:
    """
    给单张表打相关分，返回 (score, reasons)。

    权重设计(可解释)：
    - 表名(单复数/下划线归一) 命中查询 token           → 3.0
    - 同义词命中(业务词 → 目标表)                      → 2.5
    - 列名 token 命中                                   → 1.5
    - 列注释/表注释 token 命中                          → 1.2
    - 多命中相加；命中即记录原因字符串。
    """
    score = 0.0
    reasons: List[str] = []

    # 中文/英文 token 的子串互含判断：query 一个长句 token 内可能嵌着列名/注释词。
    def _hit(entry_token: str) -> bool:
        if not entry_token or len(entry_token) < 2:
            return False
        for qt in query_tokens:
            if qt == entry_token or entry_token in qt or qt in entry_token:
                return True
        return False

    # 1) 表名规范化匹配(子串或 token 相等)
    norm = entry['norm']
    for tok in query_tokens:
        tok_clean = re.sub(r'[^0-9a-z一-鿿]', '', tok)
        if not tok_clean:
            continue
        if tok_clean == norm or tok_clean in norm or norm in tok_clean:
            score += 3.0
            reasons.append(f"表名命中:{tok_clean}")
        elif norm and (norm.split()[:1] == [tok_clean] or norm.split()[-1:] == [tok_clean]):
            score += 2.0
            reasons.append(f"表名部分命中:{tok_clean}")

    # 2) 同义词命中 → 该表加分(同义词映射里出现这张表)
    for word, targets in (entry.get('synonyms') or {}).items():
        if _hit(word) and entry['table'].lower() in targets:
            score += 2.5
            reasons.append(f"同义词命中:{word}→{entry['table']}")

    # 3) 列名命中(子串互含)
    for col_tok in entry['column_tokens']:
        if _hit(col_tok):
            score += 1.5
            reasons.append(f"列名命中:{col_tok}")

    # 4) 列/表注释命中(子串互含)
    for t in entry['column_comments'] + entry['table_comment']:
        if _hit(t):
            score += 1.2
            reasons.append(f"注释命中:{t}")

    return round(score, 2), reasons


def rank_relevant_tables(
    query: str,
    index: TableIndex,
    max_tables: int,
    recent_tables: Optional[List[str]] = None,
    priority_tables: Optional[List[str]] = None,
    user_synonyms: Optional[Dict[str, List[str]]] = None,
) -> List[ScoredTable]:
    """
    对查询打分并返回 Top-K 相关表（降序）。无命中时回退 recent/priority。

    参数：
        query: 用户查询
        index: TableIndex（SchemaManager 注入）
        max_tables: 返回上限
        recent_tables: 近期使用过的表（TTL 缓存内），兜底用
        priority_tables: 配置优先级表，兜底用
        user_synonyms: settings.user_synonym_map
    """
    q = _STOP_CHARS.sub(' ', query or '').strip()
    query_tokens = _tokenize(q)
    # 去除只匹配到处处命中的超短或泛化 token（如单字）
    query_tokens = [t for t in query_tokens if len(t) >= 2]

    scored: List[ScoredTable] = []
    has_result = False

    for entry in index._tables:
        score, reasons = score_table(query_tokens, entry)
        if score > 0:
            has_result = True
            scored.append(ScoredTable(entry['table'], score, reasons))

    if has_result:
        scored.sort(key=lambda s: (-s.score, s.table))
        return scored[:max_tables]

    # 兜底：近期表 → 优先级表
    fallback: List[str] = []
    for t in (recent_tables or []):
        if t not in fallback and not index._tables or any(e['table'] == t for e in index._tables):
            fallback.append(t)
    for t in (priority_tables or []):
        if t not in fallback:
            fallback.append(t)
    return [
        ScoredTable(t, 0.0, ["兜底:无强命中，回退常用表"])
        for t in fallback[:max_tables]
    ]