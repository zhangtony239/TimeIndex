import lancedb
import pandas as pd
import numpy as np


def test_connection():
    """测试 LanceDB 连接"""
    print("测试 1: 连接 LanceDB...")
    db = lancedb.connect(".lancedb")
    print("  ✓ 连接成功")
    return db


def test_create_table(db):
    """测试创建表"""
    print("\n测试 2: 创建表...")
    
    # 创建示例数据
    data = {
        "vector": [np.random.rand(128).tolist() for _ in range(10)],
        "text": [f"文档 {i}" for i in range(10)],
        "id": list(range(10)),
    }
    df = pd.DataFrame(data)
    
    # 创建表
    table = db.create_table("test_table", data=df, mode="overwrite")
    print(f"  ✓ 表创建成功，包含 {len(df)} 条记录")
    return table


def test_query_table(db):
    """测试查询表"""
    print("\n测试 3: 向量查询...")
    
    table = db.open_table("test_table")
    
    # 生成随机查询向量
    query_vector = np.random.rand(128).tolist()
    
    # 执行向量搜索
    results = table.search(query_vector).limit(3).to_pandas()
    print(f"  ✓ 查询成功，返回 {len(results)} 条结果")
    print(f"  结果 ID: {results['id'].tolist()}")
    return results


def test_add_data(db):
    """测试添加数据"""
    print("\n测试 4: 添加数据...")
    
    table = db.open_table("test_table")
    
    # 新数据
    new_data = pd.DataFrame({
        "vector": [np.random.rand(128).tolist() for _ in range(5)],
        "text": [f"新文档 {i}" for i in range(5)],
        "id": list(range(10, 15)),
    })
    
    # 添加数据
    table.add(new_data)
    
    # 验证数据量
    count = len(table.to_pandas())
    print(f"  ✓ 添加成功，表中共有 {count} 条记录")
    return count


def test_delete_data(db):
    """测试删除数据"""
    print("\n测试 5: 删除数据...")
    
    table = db.open_table("test_table")
    
    # 删除 id < 5 的记录
    table.delete("id < 5")
    
    # 验证数据量
    count = len(table.to_pandas())
    print(f"  ✓ 删除成功，表中共有 {count} 条记录")
    return count


def test_list_tables(db):
    """测试列出所有表"""
    print("\n测试 6: 列出所有表...")
    
    tables = db.table_names()
    print(f"  ✓ 数据库中共有 {len(tables)} 个表: {tables}")
    return tables


def test_drop_table(db):
    """测试删除表"""
    print("\n测试 7: 删除表...")
    
    db.drop_table("test_table")
    tables = db.table_names()
    print(f"  ✓ 表已删除，剩余表: {tables}")


def main():
    """运行所有测试"""
    print("=" * 50)
    print("LanceDB 功能测试")
    print("=" * 50)
    
    # 测试连接
    db = test_connection()
    
    # 列出表
    test_list_tables(db)
    
    # 创建表
    test_create_table(db)
    
    # 查询数据
    test_query_table(db)
    
    # 添加数据
    test_add_data(db)
    
    # 删除数据
    test_delete_data(db)
    
    # 删除表
    test_drop_table(db)
    
    print("\n" + "=" * 50)
    print("所有测试完成!")
    print("=" * 50)


if __name__ == "__main__":
    main()
