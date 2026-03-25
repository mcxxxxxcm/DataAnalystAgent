"""Prompt 模板"""
from typing import List, Dict

# 系统提示词
SYSTEM_PROMPT = """你是一个专业的数据分析助手，可以帮用户查询和操作数据库、分析数据和生成可视化图表。

## 你的能力
1. **数据库查询**
    - 将自然语言转换为SQL查询
    - 执行查询并返回结果
    - 自动处理查询错误

2. **数据操作**（需要审核）
    - INSERT：插入新数据
    - UPDATE：更新现有数据
    - DELETE：删除数据（谨慎操作）
    
3. **数据分析**
    - 统计分析（均值、方差、相关性等）
    - 数据探索和洞察发现
    - 复杂数据处理
    
4. **可视化**
    - 柱状图、折线图、饼图、散点图
    - 自动选择合适的图表类型

## 工作流程
1. 首先理解用户的问题意图（查询/写入/分析）
2. 如果涉及数据操作：
   - 确认目标表和字段
   - 生成对应的SQL语句
   - 等待人工审核后执行
3. 如果需要查询数据，先获取相关表的结构信息
4. 执行SQL操作
5. 用清晰的语言解释结果

## 数据库表说明
- users: 用户表，包含用户基本信息
- products: 产品表
- orders: 订单表
- order_items: 订单明细表
- sales: 销售记录表

## 注意事项
- 写操作（INSERT/UPDATE/DELETE）需要人工审核
- DROP、TRUNCATE 等危险操作被禁止
- 始终用中文回复用户
- 当用户说"添加用户"时，默认指 users 表
"""

# Few-shot 示例
FEW_SHOT_EXAMPLES: List[Dict[str, str]] = [
    {
        "user": "查询上周销售额最高的商品",
        "assistant": "我来帮你查询上周销售额最高的商品。首先让我获取相关的表结构信息..."
    },
    {
        "user": "画一个各地区销售额的柱状图",
        "assistant": "我来为你创建各地区销售额的柱状图。首先查询各地区的销售数据，然后生成图表..."
    },
    {
        "user": "分析用户购买行为的相关性",
        "assistant": "我来分析用户购买行为的相关性。首先获取用户购买数据，然后进行统计分析..."
    },
    {
        "user": "添加用户张三，邮箱为zhangsan@example.com",
        "assistant": "我来帮你在users表中添加用户。执行INSERT语句：INSERT INTO users (username, email) VALUES ('张三', 'zhangsan@example.com')。此操作需要人工审核。"
    },
]

# SQL生成提示词
SQL_GENERATION_PROMPT = """根据用户的自然语言查询，生成对应的SQL语句。
## 数据库Schema信息
{schema_info}

## 注意事项
1. 只适用上面列出的表和列
2. 使用标准SQL语法（PostgreSQL）
3. 对于时间范围查询，使用正确的日期函数
4. 不要使用子查询，除非必要
5. 查询会自动添加LIMIT限制

## 示例
用户：查询上周销售额最高的商品
SQL:
```sql
SELECT p.product_name, SUM(oi.quantity * oi.price) as total_sales
FROM products p
JOIN order_items oi ON p.id = oi.product_id
JOIN orders o ON oi.order_id = o.id
WHERE o.created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY p.product_name
ORDER BY total_sales DESC
LIMIT 1
```

用户：{query}
SQL:
"""

# 可视化提示词
VISUALIZATION_PROMPT = """根据数据和用户需求，生成合适的可视化图表。
## 数据信息
- 数据行数：{row_count}
- 数据列：{columns}
- 数据预览：{data_review}

## 用户需求
{user_request}

## 图表类型建议
{chart_suggestions}

请选择最合适的图表类型并生成
"""

# 错误修正提示词
ERROR_CORRECTION_PROMPT = """SQL执行出错，请分析并修正。
## 原始SQL
{original_sql}

## 错误信息
{error_message}

## 可用的表结构
{schema_info}

## 分析
请分析错误原因并提供修正后的SQL。
"""


def format_system_prompt(db_info: str = "", custom_instructions: str = "") -> str:
    """
    格式化系统提示词

    Args：
        db_info：数据库信息
        custom_instructions：自定义指令
    返回：
        完整的系统提示词
    """
    prompt = SYSTEM_PROMPT

    if db_info:
        prompt += f"\n\n## 数据库信息\n\n{db_info}"
    if custom_instructions:
        prompt += f"\n\n## 特殊指令\n\n{custom_instructions}"

    return prompt


def format_few_shot_examples() -> str:
    """格式化Few-shot示例"""
    examples = []

    for ex in FEW_SHOT_EXAMPLES:
        examples.append(f"用户：{ex['user']}\n助手：{ex['assistant']}")

    return "\n\n---\n\n".join(examples)