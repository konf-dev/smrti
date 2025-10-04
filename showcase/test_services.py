#!/usr/bin/env python3
"""
Test all Smrti backend services connectivity
"""

import sys

def test_redis():
    """Test Redis connection"""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, decode_responses=False)
        r.ping()
        print("✅ Redis: Connected (localhost:6379)")
        return True
    except Exception as e:
        print(f"❌ Redis: Failed - {e}")
        return False

def test_chromadb():
    """Test ChromaDB connection"""
    try:
        import chromadb
        client = chromadb.HttpClient(host='localhost', port=8001)
        heartbeat = client.heartbeat()
        print(f"✅ ChromaDB: Connected (localhost:8001)")
        return True
    except Exception as e:
        print(f"❌ ChromaDB: Failed - {e}")
        return False

def test_postgres():
    """Test PostgreSQL connection"""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host='localhost',
            port=5432,
            database='smrti',
            user='smrti',
            password='smrti_password'
        )
        print("✅ PostgreSQL: Connected (localhost:5432, db=smrti, user=smrti)")
        conn.close()
        return True
    except Exception as e:
        print(f"❌ PostgreSQL: Failed - {e}")
        return False

def test_asyncpg():
    """Test asyncpg is installed"""
    try:
        import asyncpg
        print("✅ asyncpg: Installed")
        return True
    except ImportError:
        print("❌ asyncpg: Not installed")
        return False

def main():
    print("🔍 Testing Smrti Backend Services\n")
    print("=" * 60)
    
    results = {
        "Redis": test_redis(),
        "ChromaDB": test_chromadb(),
        "PostgreSQL": test_postgres(),
        "asyncpg": test_asyncpg()
    }
    
    print("=" * 60)
    print(f"\n📊 Results: {sum(results.values())}/{len(results)} services ready")
    
    if all(results.values()):
        print("\n🎉 All services are ready! You can proceed with testing.")
        return 0
    else:
        print("\n⚠️  Some services are not ready. Fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
