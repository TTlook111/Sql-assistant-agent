from __future__ import annotations

from typing import Any

import pymysql
from pymysql.connections import Connection


def introspect_schema(conn: Connection, database: str) -> dict[str, Any]:
    tables: list[dict[str, Any]] = []

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT TABLE_NAME, TABLE_COMMENT, TABLE_ROWS, ENGINE
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
            """,
            (database,),
        )
        table_rows = cur.fetchall()

        for tbl in table_rows:
            table_name = tbl["TABLE_NAME"]

            cur.execute(
                """
                SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
                       COLUMN_COMMENT, COLUMN_KEY, EXTRA
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
                """,
                (database, table_name),
            )
            columns = cur.fetchall()

            cur.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND CONSTRAINT_NAME = 'PRIMARY'
                ORDER BY ORDINAL_POSITION
                """,
                (database, table_name),
            )
            pk_rows = cur.fetchall()
            primary_keys = [r["COLUMN_NAME"] for r in pk_rows]

            cur.execute(
                """
                SELECT
                    kcu.COLUMN_NAME,
                    kcu.REFERENCED_TABLE_NAME,
                    kcu.REFERENCED_COLUMN_NAME,
                    kcu.CONSTRAINT_NAME
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                WHERE kcu.TABLE_SCHEMA = %s AND kcu.TABLE_NAME = %s
                  AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
                ORDER BY kcu.ORDINAL_POSITION
                """,
                (database, table_name),
            )
            foreign_keys = cur.fetchall()

            cur.execute(
                """
                SELECT INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS COLUMNS,
                       NON_UNIQUE
                FROM INFORMATION_SCHEMA.STATISTICS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND INDEX_NAME != 'PRIMARY'
                GROUP BY INDEX_NAME, NON_UNIQUE
                ORDER BY INDEX_NAME
                """,
                (database, table_name),
            )
            indexes = cur.fetchall()

            tables.append(
                {
                    "name": table_name,
                    "comment": tbl.get("TABLE_COMMENT", ""),
                    "engine": tbl.get("ENGINE", ""),
                    "row_count": tbl.get("TABLE_ROWS", 0),
                    "columns": columns,
                    "primary_keys": primary_keys,
                    "foreign_keys": foreign_keys,
                    "indexes": indexes,
                }
            )

    return {"database": database, "tables": tables}


def format_schema_markdown(schema: dict[str, Any]) -> str:
    lines: list[str] = [f"# 数据库 Schema: {schema['database']}", ""]

    for table in schema["tables"]:
        name = table["name"]
        comment = table.get("comment", "")
        header = f"## {name}（{comment}）" if comment else f"## {name}"
        lines.append(header)

        if table.get("row_count"):
            lines.append(f"预估行数：{table['row_count']}")
        lines.append("")

        lines.append("| 字段 | 类型 | 可空 | 默认值 | 说明 |")
        lines.append("|------|------|------|--------|------|")

        pk_set = set(table.get("primary_keys", []))
        for col in table["columns"]:
            col_name = col["COLUMN_NAME"]
            col_type = col["COLUMN_TYPE"]
            nullable = col["IS_NULLABLE"]
            default = col.get("COLUMN_DEFAULT") or ""
            comment_text = col.get("COLUMN_COMMENT", "")
            key_mark = ""
            if col_name in pk_set:
                key_mark = "（主键）"
            parts = [comment_text, key_mark]
            desc = "".join(p for p in parts if p)
            lines.append(f"| {col_name} | {col_type} | {nullable} | {default} | {desc} |")

        lines.append("")

        fks = table.get("foreign_keys", [])
        if fks:
            lines.append("**外键关系：**")
            for fk in fks:
                lines.append(
                    f"- {fk['COLUMN_NAME']} → {fk['REFERENCED_TABLE_NAME']}.{fk['REFERENCED_COLUMN_NAME']}"
                )
            lines.append("")

        indexes = table.get("indexes", [])
        if indexes:
            unique_indexes = [idx for idx in indexes if not idx["NON_UNIQUE"]]
            if unique_indexes:
                lines.append("**唯一索引：**")
                for idx in unique_indexes:
                    lines.append(f"- {idx['INDEX_NAME']}({idx['COLUMNS']})")
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def get_tables_summary(schema: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": t["name"],
            "comment": t.get("comment", ""),
            "columns_count": len(t.get("columns", [])),
            "row_count": t.get("row_count", 0),
        }
        for t in schema.get("tables", [])
    ]
