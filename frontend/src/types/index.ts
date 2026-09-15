export type MigrationStatus = 'QUEUED'|'PRECHECK'|'STARTING'|'RUNNING'|'COMPLETED'|'FAILED'|'CANCELLED';
export type MigrationMode = 'schema_and_data'|'schema_only'|'data_only';
export interface ConnectionInput { database_type: 'sqlserver'|'postgresql'; host: string; port: number; database: string; username: string; password: string; }
export interface MigrationConfig { source: ConnectionInput; destination: ConnectionInput; schema: string; tables: string[]; mode: MigrationMode; workers: number; drop_tables: boolean; confirmation: boolean; }
export interface TableInfo { name: string; estimated_rows: number; size_mb: number; }
export interface MigrationJob { id: string; status: MigrationStatus; source_database: string; destination_database: string; selected_schema: string; selected_tables: string[]; tables_processed: number; tables_failed?: number; rows_processed?: number; error_count: number; started_at?: string; completed_at?: string; exit_code?: number; failure_reason?: string; }
