In that case, you want to focus on optimizing SELECT performance, even if it means taking a hit on INSERT/UPDATE/DELETE operations. Here are the best options for precalculating values to make SELECTs faster:

Indexed Views (Materialized Views in SQL Server):

sql-- Create a view with SCHEMABINDING (required for indexing)
CREATE VIEW vw_ClusterWithFreeCores
WITH SCHEMABINDING
AS
    SELECT 
        cluster_id,
        FreeGHz,
        FreeGHz / 2.4 AS FreeCores,
        -- other important columns
    FROM dbo.YourTable;

-- Create a unique clustered index on the view
CREATE UNIQUE CLUSTERED INDEX IX_vw_ClusterWithFreeCores
ON vw_ClusterWithFreeCores(cluster_id);
This creates a materialized view that SQL Server automatically maintains when the underlying data changes. It's stored physically and will make your SELECTs much faster.

PERSISTED Computed Columns with Indexes:

sql-- Add a persisted computed column
ALTER TABLE YourTable
ADD FreeCores AS (FreeGHz / 2.4) PERSISTED;

-- Create an index on it
CREATE INDEX IX_YourTable_FreeCores ON YourTable(FreeCores);
This physically stores the calculation results in the table and indexes them for fast retrieval.

Triggers to Maintain a Separate Summary Table:

sql-- Create a summary table
CREATE TABLE FreeCoresSummary (
    cluster_id INT PRIMARY KEY,
    FreeCores DECIMAL(10,2)
);

-- Create a trigger to update it
CREATE TRIGGER trg_UpdateFreeCores
ON YourTable
AFTER INSERT, UPDATE
AS
BEGIN
    MERGE INTO FreeCoresSummary AS target
    USING (SELECT cluster_id, FreeGHz / 2.4 AS FreeCores FROM inserted) AS source
    ON target.cluster_id = source.cluster_id
    WHEN MATCHED THEN
        UPDATE SET FreeCores = source.FreeCores
    WHEN NOT MATCHED THEN
        INSERT (cluster_id, FreeCores) VALUES (source.cluster_id, source.FreeCores);
END;
The indexed view option is generally the best choice when you're prioritizing SELECT performance over write operations. SQL Server handles all the maintenance automatically, and your queries can be extremely fast.