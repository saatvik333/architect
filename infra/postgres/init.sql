-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Code embeddings table for semantic search
CREATE TABLE IF NOT EXISTS code_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    root_path TEXT NOT NULL,
    file_path TEXT NOT NULL,
    symbol_name TEXT NOT NULL,
    symbol_kind TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    embedding vector(384) NOT NULL,
    source_chunk TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_embeddings_root_path ON code_embeddings(root_path);

-- Create additional databases needed by Temporal
CREATE DATABASE temporal;
CREATE DATABASE temporal_visibility;

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE temporal TO architect;
GRANT ALL PRIVILEGES ON DATABASE temporal_visibility TO architect;
