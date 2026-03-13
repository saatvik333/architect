-- Create additional databases needed by Temporal
CREATE DATABASE temporal;
CREATE DATABASE temporal_visibility;

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE temporal TO architect;
GRANT ALL PRIVILEGES ON DATABASE temporal_visibility TO architect;
