import { z } from 'zod';
export const connectionSchema
    = z.object({ database_type: z.enum(['sqlserver','postgresql']), host: z.string().min(1, 'Host is required'),
    port: z.coerce.number().int().min(1).max(65535), database: z.string().min(1, 'Database is required'),
    username: z.string().min(1, 'Username is required'), password: z.string().min(1, 'Password is required') });
export const migrationSchema
    = z.object({ source: connectionSchema, destination: connectionSchema, schema: z.string().min(1),
    tables: z.array(z.string()).min(1, 'Select at least one table'), mode: z.enum(['schema_and_data','schema_only','data_only']),
    workers: z.coerce.number().int().min(1).max(32), drop_tables: z.boolean(), confirmation: z.boolean() });
export type MigrationForm = z.infer<typeof migrationSchema>;
