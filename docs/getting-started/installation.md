# Installation

## Requirements

- **Python 3.11+**
- **PostgreSQL 15+** with the pgvector extension (0.5+)
- An embedding provider: **Ollama** (local, free) or **OpenAI** (cloud, API key required)

## Install smrti

```bash
pip install smrti
```

## Set up PostgreSQL

smrti stores everything in PostgreSQL. You need a running instance with the pgvector extension enabled. Pick whichever option fits your setup.

### Option A: Local PostgreSQL

If you already have PostgreSQL installed locally:

```bash
# Check your version (must be 15 or higher)
psql --version

# Create a database for smrti
createdb smrti_dev
```

Then install the pgvector extension (see the pgvector section below).

### Option B: Docker

The fastest way to get a pgvector-ready database running:

```bash
docker run -d \
  --name smrti-postgres \
  -e POSTGRES_USER=smrti \
  -e POSTGRES_PASSWORD=smrti \
  -e POSTGRES_DB=smrti_dev \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

The `pgvector/pgvector` image ships with the extension pre-installed. No additional setup needed — skip straight to the Ollama or OpenAI section.

Your connection string will be:

```
postgresql://smrti:smrti@localhost:5432/smrti_dev
```

### Option C: Cloud (Supabase or Neon)

Both [Supabase](https://supabase.com) and [Neon](https://neon.tech) offer managed PostgreSQL with pgvector support on their free tiers.

**Supabase:**

1. Create a new project at [supabase.com](https://supabase.com)
2. Go to Settings > Database to find your connection string
3. pgvector is already enabled — no extra steps

**Neon:**

1. Create a new project at [neon.tech](https://neon.tech)
2. Copy the connection string from the dashboard
3. Enable pgvector by running `CREATE EXTENSION vector;` in the SQL editor

Your connection string will look like:

```
postgresql://user:password@ep-something.region.aws.neon.tech/neondb?sslmode=require
```

## Install the pgvector extension

If you are using Docker with the `pgvector/pgvector` image, or a cloud provider that ships pgvector, skip this step.

For a local PostgreSQL installation, you need to install pgvector yourself:

```bash
# Ubuntu / Debian
sudo apt install postgresql-16-pgvector

# macOS with Homebrew
brew install pgvector

# From source (any platform)
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make && sudo make install
```

Then enable it in your database:

```bash
psql -d smrti_dev -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

smrti also uses the `pg_trgm` extension for fuzzy text search. It ships with PostgreSQL by default, but you can enable it explicitly:

```bash
psql -d smrti_dev -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

Note: smrti runs migrations automatically on first connect, so these extensions will be created for you if your database user has the required privileges. The commands above are only needed if your user does not have `CREATE EXTENSION` permission.

## Set up an embedding provider

smrti needs an embedding provider to convert text into vectors for semantic search. You have two options.

### Option A: Ollama (local, free)

[Ollama](https://ollama.com) runs embedding models locally on your machine. No API key, no network calls, no cost.

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull an embedding model
ollama pull nomic-embed-text
```

Verify Ollama is running:

```bash
curl http://localhost:11434/api/tags
```

You should see `nomic-embed-text` in the model list.

### Option B: OpenAI

If you prefer cloud embeddings, set your API key as an environment variable:

```bash
export OPENAI_API_KEY="sk-..."
```

Or pass it directly in your code (see the verification step below).

## Verify the installation

Run this script to confirm everything is wired up correctly:

```python
import asyncio
from smrti import Memory, SmrtiConfig
from smrti.embedding import OllamaEmbedding  # or OpenAIEmbedding

async def verify():
    config = SmrtiConfig(
        dsn="postgresql://smrti:smrti@localhost:5432/smrti_dev",
        embedding_provider=OllamaEmbedding(),  # uses nomic-embed-text by default
    )
    memory = Memory(config)
    await memory.connect()

    # Add a test node
    result = await memory.add_nodes([
        {"node_type": "test", "content": "Hello from smrti!"}
    ])
    print(f"Created node: {result['node_ids'][0]}")

    # Search for it
    results = await memory.search("hello")
    print(f"Found {len(results['results'])} result(s)")

    await memory.close()
    print("Installation verified.")

asyncio.run(verify())
```

If you are using OpenAI instead of Ollama, replace the embedding provider:

```python
from smrti.embedding import OpenAIEmbedding

config = SmrtiConfig(
    dsn="postgresql://smrti:smrti@localhost:5432/smrti_dev",
    embedding_provider=OpenAIEmbedding(api_key="sk-..."),
)
```

If the script prints "Installation verified." without errors, you are ready to go. Head to the [Quickstart](quickstart.md) to start building.
