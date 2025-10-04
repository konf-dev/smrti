# 🧪 Smrti Testing & Learning Log

**Purpose**: Document everything we discover while testing Smrti - what works, what doesn't, and how to fix it.

---

## 📅 Testing Session 1 - Oct 4, 2025

### 🎯 Goal
Test the actual implemented functionality of Smrti to understand what works before building higher-level features.

---

## ✅ Fixed Issues (Pre-Testing)

### Issue #1: Import Errors
**Problem**: `ImportError: cannot import name 'Smrti'`
**Root Cause**: Classes not exported in `__init__.py`, circular imports
**Solution**: Added exports, renamed api/ to api_old/, added missing exception classes
**Status**: ✅ FIXED

### Issue #2: AdapterRegistry Instantiation
**Problem**: `Can't instantiate abstract class AdapterRegistry`
**Root Cause**: Using Protocol instead of concrete implementation
**Solution**: Import and use `SmrtiAdapterRegistry`
**Status**: ✅ FIXED

### Issue #3: Missing Registry Properties
**Problem**: `AttributeError: object has no attribute 'tier_stores'`
**Root Cause**: Private attributes not exposed
**Solution**: Added @property methods for all registries
**Status**: ✅ FIXED

### Issue #4: Missing register_memory_tier
**Problem**: Method doesn't exist but API calls it
**Solution**: Added as alias to `register_smrti_provider()`
**Status**: ✅ FIXED

### Issue #5: Adapter Configuration
**Problem**: Wrong import paths, incorrect constructor args
**Solution**: Fixed imports and added tier_name positional args
**Status**: ✅ FIXED

---

## 🧪 Current Testing Phase

### What We're Testing
- [ ] System initialization and shutdown
- [ ] Direct tier access (low-level API)
- [ ] Working Memory (Redis with TTL)
- [ ] Short-Term Memory (Redis with sessions)
- [ ] Long-Term Memory (ChromaDB with embeddings)
- [ ] Episodic Memory (PostgreSQL with timestamps)
- [ ] Memory retrieval from each tier
- [ ] Registry functionality
- [ ] Adapter health checks

### Known Gaps (Not Testing Yet)
- ❌ `store_memory()` - Not implemented
- ❌ `search_memories()` - Not implemented
- ❌ Automatic tier routing - Doesn't exist
- ❌ Content validation - Not implemented
- ❌ Consolidation engine - Unclear functionality

---

## 📝 Test Results

### Session 1 - Initial Testing (Oct 4, 2025)

#### Issue #7: Memory Tiers Not Initialized
**Problem**: `AttributeError: 'NoneType' object has no attribute 'store'`
**Root Cause**: Memory tiers require their backend services to be running:
- Working/Short-Term Memory → Requires Redis
- Long-Term Memory → Requires ChromaDB package
- Episodic Memory → Requires PostgreSQL with proper config

**Warnings from initialization**:
```
WARNING: Failed to initialize ChromaDB adapter: chromadb package is required
WARNING: Failed to initialize PostgreSQL adapter: Missing required configuration for adapter episodic: ['user']
```

**Solution**: 
1. Install ChromaDB: `pip install chromadb` ✅ DONE
2. Start Redis: `docker run -d -p 6379:6379 redis` ✅ ALREADY RUNNING
3. Start PostgreSQL (optional): Already running via docker-compose ✅ ALREADY RUNNING
4. Install asyncpg/psycopg2: `pip install asyncpg psycopg2-binary` ✅ DONE
5. **Fix Configuration**: 
   - ChromaDB port: 8001 (not 8000)
   - PostgreSQL user: `smrti` (not `postgres`)
   - PostgreSQL password: `smrti_password` (not `postgres`)

**Status**: ✅ FIXED - All services are now connected

**Test Results**:
```bash
$ python showcase/test_services.py
✅ Redis: Connected (localhost:6379)
✅ ChromaDB: Connected (localhost:8001)
✅ PostgreSQL: Connected (localhost:5432, db=smrti, user=smrti)
✅ asyncpg: Installed

📊 Results: 4/4 services ready
🎉 All services are ready! You can proceed with testing.
```

#### Issue #8: Unhealthy Docker Services
**Problem**: 4 Docker services showing as "unhealthy" (ChromaDB, Neo4j, Jaeger, Jupyter)
**Root Cause**: Health check commands using `curl` which isn't available in minimal container images

**Error Example**:
```
OCI runtime exec failed: exec: "curl": executable file not found in $PATH
```

**Solution**: 
1. **ChromaDB**: Changed from `curl` to TCP check: `timeout 2 bash -c '</dev/tcp/localhost/8000'`
2. **Neo4j**: Changed from `curl` to TCP check: `timeout 2 bash -c '</dev/tcp/localhost/7687'` + removed corrupted volumes
3. **Jaeger**: Changed from `curl` to `wget` (available in jaeger image)
4. **Added missing volumes**: neo4j-import, neo4j-plugins

**Docker Commands Used**:
```bash
# Recreate containers with new healthcheck config
docker-compose up -d chroma neo4j jaeger

# For Neo4j - had to clear corrupted data
docker-compose down neo4j
docker volume rm smrti_neo4j-data smrti_neo4j-logs
docker-compose up -d neo4j
```

**Status**: ✅ FIXED

**Final Service Status**:
```bash
✅ Redis        - Healthy (Working Memory)
✅ PostgreSQL   - Healthy (Short-term Memory)
✅ ChromaDB     - Healthy (Long-term Memory)
✅ Neo4j        - Healthy (Semantic/Graph Memory)
✅ Jaeger       - Healthy (Tracing)
✅ Prometheus   - Healthy (Metrics)
✅ Grafana      - Healthy (Monitoring)
```

---

### Test Results Will Be Recorded Here

---

## 💡 Key Learnings

### Learnings Will Be Documented Here

---

## 🐛 Issues Discovered

### New Issues Will Be Logged Here

---

## 🚀 Next Steps

1. Run comprehensive test of low-level tier access
2. Document what works and what doesn't
3. Fix any issues discovered
4. Build high-level API based on validated functionality
5. Create use case showcases once API is stable

---

## 📚 References

- **Code Analysis**: `docs/CURRENT_STATE_ANALYSIS.md`
- **User Documentation**: `docs/smrti-prd.md`
- **Main Test Notebook**: `showcase/smrti_comprehensive_test.ipynb`
