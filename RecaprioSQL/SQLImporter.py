# Import necessary libraries
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import pyodbc
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("sql_importer")

# Create FastAPI app
app = FastAPI(title="SQL Importer Service", 
              description="Service to import cluster data to SQL Server")

# Define data models
class ClusterProperty(BaseModel):
    cluster_name: str
    environment: Optional[str] = None
    region: Optional[str] = None
    owner: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True

class ClusterStat(BaseModel):
    timestamp: datetime
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    storage_usage: Optional[float] = None
    network_throughput: Optional[float] = None
    active_connections: Optional[int] = None
    request_count: Optional[int] = None
    response_time_ms: Optional[int] = None
    error_count: Optional[int] = None
    FreeGHz: Optional[float] = None

class ClusterData(BaseModel):
    properties: ClusterProperty
    stats: List[ClusterStat]

class ImportRequest(BaseModel):
    clusters: List[ClusterData] = Field(..., description="List of clusters with properties and stats")

# Database connection function
def get_db_connection():
    connection_string = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=your_server_name;"
        "DATABASE=your_database_name;"
        "UID=your_username;"
        "PWD=your_password;"
        "Trusted_Connection=yes;"  # Remove if using UID/PWD
    )
    try:
        conn = pyodbc.connect(connection_string)
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

@app.post("/import", status_code=201)
async def import_data(request: ImportRequest = Body(...)):
    """
    Import cluster data to SQL Server using table-valued parameters for maximum efficiency
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Begin transaction for atomicity
        cursor.execute("BEGIN TRANSACTION")
        
        # Use SQL Server's JSON capabilities for bulk insert
        for cluster in request.clusters:
            # 1. Insert or update cluster properties
            properties_json = json.dumps(cluster.properties.dict())
            stats_json = json.dumps([stat.dict() for stat in cluster.stats])
            
            # Using SQL Server's JSON capabilities for efficient processing
            cursor.execute("""
                DECLARE @cluster_id INT;
                
                -- Insert or update cluster properties and get cluster_id
                MERGE INTO ClusterProperties AS target
                USING (
                    SELECT 
                        name, 
                        environment, 
                        region, 
                        owner, 
                        description, 
                        is_active
                    FROM OPENJSON(@properties_json) WITH (
                        name NVARCHAR(100) '$.cluster_name',
                        environment NVARCHAR(50) '$.environment',
                        region NVARCHAR(50) '$.region',
                        owner NVARCHAR(100) '$.owner',
                        description NVARCHAR(MAX) '$.description',
                        is_active BIT '$.is_active'
                    )
                ) AS source (name, environment, region, owner, description, is_active)
                ON target.cluster_name = source.name
                WHEN MATCHED THEN
                    UPDATE SET 
                        environment = source.environment,
                        region = source.region,
                        owner = source.owner,
                        description = source.description,
                        is_active = source.is_active,
                        last_updated = GETDATE()
                WHEN NOT MATCHED THEN
                    INSERT (cluster_name, environment, region, owner, description, is_active)
                    VALUES (source.name, source.environment, source.region, source.owner, source.description, source.is_active)
                OUTPUT INSERTED.cluster_id;
                
                SET @cluster_id = SCOPE_IDENTITY();
                
                -- Bulk insert stats using JSON
                INSERT INTO ClusterStats (
                    cluster_id, 
                    timestamp, 
                    cpu_usage, 
                    memory_usage, 
                    storage_usage, 
                    network_throughput, 
                    active_connections, 
                    request_count, 
                    response_time_ms, 
                    error_count,
                    FreeGHz
                )
                SELECT
                    @cluster_id,
                    CONVERT(DATETIME, timestamp),
                    cpu_usage,
                    memory_usage,
                    storage_usage,
                    network_throughput,
                    active_connections,
                    request_count,
                    response_time_ms,
                    error_count,
                    FreeGHz
                FROM OPENJSON(@stats_json) WITH (
                    timestamp NVARCHAR(50) '$.timestamp',
                    cpu_usage DECIMAL(5,2) '$.cpu_usage',
                    memory_usage DECIMAL(5,2) '$.memory_usage',
                    storage_usage DECIMAL(5,2) '$.storage_usage',
                    network_throughput DECIMAL(10,2) '$.network_throughput',
                    active_connections INT '$.active_connections',
                    request_count INT '$.request_count',
                    response_time_ms INT '$.response_time_ms',
                    error_count INT '$.error_count',
                    FreeGHz DECIMAL(10,2) '$.FreeGHz'
                );
            """, (properties_json, stats_json))
        
        # Commit the transaction
        cursor.execute("COMMIT TRANSACTION")
        
        # Update statistics to ensure query optimizer has latest info for SELECT performance
        cursor.execute("EXEC sp_updatestats")
        
        return {"status": "success", "message": f"Imported {len(request.clusters)} clusters with their stats"}
        
    except Exception as e:
        # Rollback on error
        cursor.execute("IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION")
        logger.error(f"Import failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
    
    finally:
        cursor.close()
        conn.close()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)