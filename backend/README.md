# 后端说明

## 缓存机制

| 缓存类型 | 存储位置 | 过期策略 | 说明 |
|---|---|---|---|
| 基金信息 | SQLite `fund_info` | 净值1天过期，名称/类型不过期 | 基金名称、类型、最新净值 |
| 股票持仓 | SQLite `fund_holdings` | 7天过期 | 基金持仓股票明细 |
| 债券持仓 | SQLite `fund_bond_holdings` | 7天过期 | 基金债券持仓明细 |
| 行业分类 | SQLite `stock_industry` | 不自动过期 | A 股行业分类，建议每月手动更新 |
| 持仓净值 | 内存 `_nav_cache` | 15分钟过期 | 自选基金持仓计算用的最新净值 |

## 清除缓存

### 清除全部基金缓存

```bash
python -X utf8 -c "
from app.db import get_connection, init_tables
init_tables()
conn = get_connection()
conn.execute('DELETE FROM fund_info')
conn.execute('DELETE FROM fund_holdings')
conn.execute('DELETE FROM fund_bond_holdings')
conn.commit()
conn.close()
print('已清除全部基金缓存')
"
```

### 清除指定基金缓存

```bash
python -X utf8 -c "
from app.db import get_connection, init_tables
init_tables()
conn = get_connection()
code = '016881'
conn.execute('DELETE FROM fund_info WHERE fund_code = ?', (code,))
conn.execute('DELETE FROM fund_holdings WHERE fund_code = ?', (code,))
conn.execute('DELETE FROM fund_bond_holdings WHERE fund_code = ?', (code,))
conn.commit()
conn.close()
print(f'已清除 {code} 缓存')
"
```

### 清除行业缓存

```bash
python -X utf8 -c "
from app.db import get_connection, init_tables
init_tables()
conn = get_connection()
conn.execute('DELETE FROM stock_industry')
conn.commit()
conn.close()
print('已清除行业缓存')
"
```

清除后建议重新构建行业数据：

```bash
python -X utf8 build_industry_cache.py
```

### 清除内存缓存

重启后端服务即可，内存中的净值缓存会重置。

### 删除数据库（最彻底）

```bash
rm app/data/fund_data.db
```

下次请求会自动重建表，但**自选列表和聊天记录也会丢失**。

## 更新行业数据

```bash
python -X utf8 build_industry_cache.py
```

遍历全部 A 股（约5500只），获取行业分类写入数据库，预计耗时25分钟。建议每月执行一次。
