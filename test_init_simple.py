#!/usr/bin/env python3
"""Simple test to verify Smrti initialization works."""

import asyncio
from smrti.api import Smrti, SmrtiConfig

async def main():
    print("="*60)
    print("Testing Smrti Initialization")
    print("="*60)
    
    # Create config
    config = SmrtiConfig(
        default_tenant_id="test",
        redis_config={
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "decode_responses": False
        },
        chroma_config={
            "host": "localhost",
            "port": 8001,
            "persist_directory": "./chroma_data"
        },
        postgres_config={
            "host": "localhost",
            "port": 5432,
            "database": "smrti",
            "user": "smrti",
            "password": "smrti_password"
        },
        sentence_transformers_config={
            "model_name": "all-MiniLM-L6-v2"
        },
        log_level="INFO"
    )
    
    print("\n✅ Config created")
    
    # Initialize Smrti
    smrti = Smrti(config=config)
    await smrti.initialize()
    
    print("\n✅ Smrti initialized")
    
    # Check health
    health = await smrti.get_health_status()
    print(f"\n📊 Health Status: {health['status']}")
    
    # Check tiers
    print("\n📊 Memory Tiers:")
    print(f"   Working Memory: {smrti.working_memory}")
    print(f"   Short-term Memory: {smrti.short_term_memory}")
    print(f"   Long-term Memory: {smrti.long_term_memory}")
    print(f"   Episodic Memory: {smrti.episodic_memory}")
    
    # Get system stats
    stats = await smrti.get_system_stats()
    print(f"\n📊 System Stats:")
    print(f"   Adapters: {len(stats.get('adapters', {}))}")
    print(f"   Tiers: {len(stats.get('tiers', {}))}")
    
    # Shutdown
    await smrti.shutdown()
    print("\n✅ Shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
