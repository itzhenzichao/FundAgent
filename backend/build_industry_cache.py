import akshare as ak
import efinance as ef
import sqlite3
import os
import sys
import re
import time
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', write_through=True)

# 使用和 app/db.py 相同的数据库路径
from app.db import DB_FILE

# 请求间隔（秒）
REQUEST_DELAY = 0.3
# 失败后等待（秒）
FAIL_DELAY = 2
# 最大连续失败数
MAX_CONSECUTIVE_FAIL = 10
LONG_PAUSE = 30


def extract_primary_industry(board_names: list) -> str | None:
    """从板块名称列表提取一级行业"""
    exclude_keywords = [
        '板块', '概念', 'HS300', '上证', '深证', 'MSCI', '富时', '标普',
        '证金', '融资', '深股通', '沪股通', '股通', '权重', '价值', '大盘',
        '中小', '破净', '重仓', '风格', '互联', '茅指数', '宁组合', '百元',
        '央视', '热股', '龙头', '品牌', '转债', 'AH股', '成份', '综', '内卷',
    ]
    for name in board_names:
        if re.search(r'[ⅡⅢⅣⅤ]', name):
            continue
        if any(kw in name for kw in exclude_keywords):
            continue
        if re.match(r'.*\d+_', name):
            continue
        return name
    return None


def build_industry_map():
    print("开始构建行业映射表...")
    print("策略：遍历全部A股，用 efinance 获取每只股票的行业分类")

    # 1. 初始化数据库
    from app.db import init_tables
    init_tables()

    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_industry (
            stock_code TEXT PRIMARY KEY,
            industry TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    now = datetime.now().isoformat()

    # 2. 获取全部A股股票代码列表
    print("获取A股股票列表...")
    try:
        stock_df = ak.stock_info_a_code_name()
        total = len(stock_df)
        print(f"共 {total} 只A股股票")
    except Exception as e:
        print(f"获取股票列表失败: {e}")
        conn.close()
        return

    codes = stock_df['code'].tolist()

    # 3. 清空旧数据
    conn.execute("DELETE FROM stock_industry")

    success = 0
    fail = 0
    unmatched = 0
    consecutive_fail = 0

    # 4. 逐只获取行业分类
    for i, code in enumerate(codes):
        try:
            time.sleep(REQUEST_DELAY)
            df = ef.stock.get_belong_board(code)
            if df.empty:
                unmatched += 1
                continue

            board_names = df['板块名称'].tolist()
            industry = extract_primary_industry(board_names)

            if industry:
                conn.execute(
                    "INSERT OR REPLACE INTO stock_industry (stock_code, industry, updated_at) VALUES (?, ?, ?)",
                    (code, industry, now)
                )
                success += 1
            else:
                unmatched += 1

            consecutive_fail = 0

            # 每100只提交一次并打印进度
            if (i + 1) % 100 == 0:
                conn.commit()
                elapsed_per = REQUEST_DELAY + 0.05
                remaining = (total - i - 1) * elapsed_per
                print(f"进度: {i+1}/{total}, 成功={success}, 未匹配={unmatched}, 失败={fail}, 预计剩余{remaining:.0f}秒")

        except Exception as e:
            fail += 1
            consecutive_fail += 1
            print(f"股票 {code} 查询失败: {e}")
            if consecutive_fail >= MAX_CONSECUTIVE_FAIL:
                print(f"连续{consecutive_fail}次失败，暂停{LONG_PAUSE}秒...")
                time.sleep(LONG_PAUSE)
                consecutive_fail = 0
            else:
                time.sleep(FAIL_DELAY)

    # 5. 最终提交
    conn.commit()

    # 6. 统计
    count = conn.execute("SELECT COUNT(*) FROM stock_industry").fetchone()[0]
    industries = conn.execute("SELECT industry, COUNT(*) as cnt FROM stock_industry GROUP BY industry ORDER BY cnt DESC").fetchall()
    conn.close()

    print(f"\n构建完成！")
    print(f"成功映射: {success} 只, 未匹配行业: {unmatched} 只, 失败: {fail} 只")
    print(f"数据库中共 {count} 条记录")
    print(f"\n行业分布（共 {len(industries)} 个行业）:")
    for ind_name, cnt in industries:
        print(f"  {ind_name}: {cnt} 只")
    print(f"\n数据库文件: {DB_FILE}")
    print(f"更新时间: {now}")
    print("\n提示: 定期运行此脚本以更新行业分类数据（建议每月更新一次）")


if __name__ == "__main__":
    build_industry_map()
