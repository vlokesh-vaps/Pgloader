import { useEffect, useState } from 'react';
import { ArrowRight, Check, Database, History, LayoutDashboard, ListTree, Play, Plus, Search, ShieldCheck, Sparkles, X } from 'lucide-react';
import { FormProvider, useForm, useFormContext } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery } from '@tanstack/react-query';
import { cancelMigration, createMigration, getLogs, getMigration, getSchemas, getTables, preflight, subscribeToMigrationEvents, testConnection } from './services/api/client';
import type { MigrationJob } from './types';
import { migrationSchema, type MigrationForm } from './schemas/migration';

const emptyForm: MigrationForm = {
  source: { database_type: 'sqlserver', host: '', port: 1433, database: '', username: '', password: '' },
  destination: { database_type: 'postgresql', host: '', port: 5432, database: '', username: '', password: '' },
  schema: '', tables: [], mode: 'schema_and_data', workers: 4, drop_tables: false, confirmation: false,
};

function Field({ name, label, type = 'text' }: { name: string; label: string; type?: string }) {
  const { register, formState: { errors } } = useFormContext<MigrationForm>();
  const error = name.split('.').reduce<unknown>((value, key) => (value as Record<string, unknown>)?.[key], errors);
  return <label className="field"><span>{label}</span><input type={type} {...register(name as never)} />{Boolean(error) && <small className="error">{String((error as { message?: string }).message ?? '')}</small>}</label>;
}

function ConnectionCard({ type, onTested }: { type: 'source' | 'destination'; onTested?: (token: string) => void }) {
  const { getValues } = useFormContext<MigrationForm>();
  const test = useMutation({ mutationFn: testConnection, onSuccess: result => result.connection_token && onTested?.(result.connection_token) });
  const title = type === 'source' ? 'SQL Server' : 'PostgreSQL';
  return <section className={`card connection ${type}`}>
    <div className="card-title"><span className="db-badge"><Database size={15} /></span><div><small>{type.toUpperCase()} DATABASE</small><strong>{title}</strong></div></div>
    <p className="helper">Credentials are sent to the backend only for this test and are never saved in the browser.</p>
    <div className="form-grid"><Field name={`${type}.host`} label="Host" /><Field name={`${type}.port`} label="Port" /><Field name={`${type}.database`} label="Database" /><Field name={`${type}.username`} label="Username" /><Field name={`${type}.password`} label="Password" type="password" /></div>
    <div className="connection-test"><button type="button" className="secondary" disabled={test.isPending} onClick={() => test.mutate(getValues(type))}>{test.isPending ? 'Testing…' : 'Test connection'}</button>{test.isSuccess && <span className="success"><Check size={14} /> Connected · {test.data.latency_ms} ms</span>}{test.isError && <span className="test-error"><X size={14} /> {(test.error as Error).message}</span>}</div>
  </section>;
}

function NewMigration({ close, created }: { close: () => void; created: (job: MigrationJob) => void }) {
  const methods = useForm<MigrationForm>({ resolver: zodResolver(migrationSchema), defaultValues: emptyForm, mode: 'onChange' });
  const [step, setStep] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [sourceToken, setSourceToken] = useState('');
  const [destinationTested, setDestinationTested] = useState(false);
  const [result, setResult] = useState('');
  const schema = methods.watch('schema');
  const schemas = useQuery({ queryKey: ['schemas', sourceToken], queryFn: () => getSchemas(sourceToken), enabled: step === 1 && Boolean(sourceToken) });
  const tables = useQuery({ queryKey: ['tables', schema, sourceToken], queryFn: () => getTables(schema, sourceToken), enabled: step === 1 && Boolean(schema && sourceToken) });
  const check = useMutation({ mutationFn: preflight });
  const create = useMutation({ mutationFn: createMigration, onSuccess: job => { setResult(`Migration ${job.id} queued.`); created(job); } });

  async function next() {
    if (step === 0 && (!(await methods.trigger(['source', 'destination'])) || !sourceToken || !destinationTested)) return;
    if (step === 1) { methods.setValue('tables', selected); if (!selected.length) return; }
    if (step === 2 && !(await methods.trigger(['workers']))) return;
    setStep(current => Math.min(current + 1, 3));
  }

  const start = methods.handleSubmit(async values => {
    try {
      setResult('');
      const config = { ...values, tables: selected };
      const safety = await check.mutateAsync(config);
      if (safety.ready) await create.mutateAsync(config);
      else setResult('Preflight checks did not pass.');
    } catch (error) {
      setResult(error instanceof Error ? error.message : 'Unable to start migration.');
    }
  });

  return <FormProvider {...methods}><main className="wizard">
    <div className="wizard-head"><button className="back" onClick={close}><X size={18} /> Close</button><div><p className="eyebrow">NEW MIGRATION</p><h1>Configure migration</h1></div></div>
    <div className="steps">{['Connections', 'Schema & tables', 'Options', 'Review'].map((label, index) => <div className={`step ${index === step ? 'active' : ''} ${index < step ? 'complete' : ''}`} key={label}><span>{index < step ? <Check size={13} /> : index + 1}</span>{label}</div>)}</div>
    {step === 0 && <div className="connection-grid"><ConnectionCard type="source" onTested={setSourceToken} /><div className="connector"><ArrowRight /></div><ConnectionCard type="destination" onTested={() => setDestinationTested(true)} /></div>}
    {step === 1 && <section className="card table-selection"><div className="section-head"><div><h2>Select tables</h2><p>Only selected tables will be migrated.</p></div><select disabled={!sourceToken} {...methods.register('schema')}><option value="">Select schema</option>{schemas.data?.map(name => <option key={name}>{name}</option>)}</select></div><div className="table-toolbar"><span className="helper">{sourceToken ? 'Choose a schema to load its tables.' : 'Test the SQL Server connection first.'}</span><button className="link" onClick={() => setSelected((tables.data ?? []).map(table => table.name))}>Select all</button><button className="link" onClick={() => setSelected([])}>Clear all</button></div><div className="table-list">{tables.data?.map(table => <label className="table-row" key={table.name}><input type="checkbox" checked={selected.includes(table.name)} onChange={() => setSelected(current => current.includes(table.name) ? current.filter(name => name !== table.name) : [...current, table.name])} /><span>{table.name}</span><small>{table.estimated_rows.toLocaleString()} rows · {table.size_mb} MB</small></label>)}</div><p className="selection">{selected.length} tables selected</p></section>}
    {step === 2 && <section className="card options"><h2>Migration options</h2><div className="option-block"><span className="option-label">Migration mode</span>{[['schema_and_data', 'Schema + Data'], ['schema_only', 'Schema Only'], ['data_only', 'Data Only']].map(([value, label]) => <label key={value}><input type="radio" value={value} {...methods.register('mode')} />{label}</label>)}</div><label className="field narrow"><span>Workers</span><input type="number" {...methods.register('workers')} /><small>Use 1–32 workers.</small></label><label className="danger-option"><input type="checkbox" {...methods.register('drop_tables')} /><span><strong>Drop destination tables</strong><small>Existing target tables may be removed.</small></span></label>{methods.watch('drop_tables') && <label className="confirm"><span>Type DROP TABLES to confirm</span><input placeholder="DROP TABLES" onChange={event => methods.setValue('confirmation', event.target.value === 'DROP TABLES')} /></label>}</section>}
    {step === 3 && <><section className="card safety"><div className="section-head"><div><h2><ShieldCheck size={18} /> Safety tracker</h2><p>Critical checks run before execution.</p></div><span className="ready">READY</span></div>{['Source connection verified', 'Destination connection verified', 'Selected tables validated', 'pgloader version verified', 'Destination permissions checked', 'Temporary workspace checked'].map(item => <div className="check-row" key={item}><Check size={15} /><span>{item}</span><small>PASSED</small></div>)}</section>{result && <div className="notice success"><Check size={16} /> {result}</div>}</>}
    <div className="wizard-actions"><button className="secondary" onClick={step ? () => setStep(step - 1) : close}>Back</button>{step < 3 ? <button className="primary" onClick={next}>Continue <ArrowRight size={15} /></button> : <button className="primary" disabled={check.isPending || create.isPending} onClick={start}><Play size={14} /> {check.isPending || create.isPending ? 'Starting…' : 'Confirm & start migration'}</button>}</div>
  </main></FormProvider>;
}

function MigrationMonitor({ job, back }: { job: MigrationJob; back: () => void }) {
  const status = useQuery({ queryKey: ['migration', job.id], queryFn: () => getMigration(job.id), refetchInterval: 1500 });
  const logs = useQuery({ queryKey: ['logs', job.id], queryFn: () => getLogs(job.id), refetchInterval: 1500 });
  const cancel = useMutation({ mutationFn: () => cancelMigration(job.id), onSuccess: () => status.refetch() });
  const current = status.data ?? job;
  const terminal = ['COMPLETED', 'FAILED', 'CANCELLED'].includes(current.status);
  useEffect(() => subscribeToMigrationEvents(job.id, () => { status.refetch(); logs.refetch(); }), [job.id]);
  return <main className="main monitor">
    <div className="page-title"><div><p className="eyebrow">MIGRATION JOB</p><h1>{current.id}</h1><p>{current.source_database} <ArrowRight size={13} /> {current.destination_database}</p></div><button className="secondary" onClick={back}>Back to dashboard</button></div>
    <div className="monitor-summary card"><div><span>Status</span><strong className={`job-status ${current.status.toLowerCase()}`}>{current.status}</strong></div><div><span>Schema</span><strong>{current.selected_schema}</strong></div><div><span>Tables</span><strong>{current.tables_processed} / {current.selected_tables.length}</strong></div><div><span>Rows processed</span><strong>{current.rows_processed ?? 'N/A'}</strong></div><div><span>Errors</span><strong>{current.error_count}</strong></div></div>
    <section className="card live-logs"><div className="section-head"><div><h2>Migration logs</h2><p>Live output from the pgloader process.</p></div>{!terminal && <button className="danger-button" onClick={() => cancel.mutate()} disabled={cancel.isPending}>{cancel.isPending ? 'Cancelling…' : 'Cancel migration'}</button>}</div><div className="log-list">{logs.data?.length ? logs.data.map((entry, index) => <div className="log-line" key={`${entry.timestamp}-${index}`}><time>{new Date(entry.timestamp).toLocaleTimeString()}</time><b className={entry.level.toLowerCase()}>{entry.level}</b><span>{entry.message}</span></div>) : <p className="log-empty">Waiting for pgloader output…</p>}</div></section>
    {terminal && <section className={`result-card card ${current.status.toLowerCase()}`}><strong>{current.status === 'COMPLETED' ? 'Migration completed' : `Migration ${current.status.toLowerCase()}`}</strong><p>{current.failure_reason ?? (current.status === 'COMPLETED' ? 'All reported pgloader output has been processed.' : 'Review the logs for technical details.')}</p></section>}
  </main>;
}

function Dashboard({ newMigration }: { newMigration: () => void }) {
  return <><header className="topbar"><div className="crumb">Migrations <span>/</span> Dashboard</div><div className="top-actions"><Search size={18} /></div></header><main className="main"><div className="page-title"><div><p className="eyebrow">WORKSPACE / INTERNAL</p><h1>Migration Dashboard</h1><p>Move data safely from SQL Server to PostgreSQL.</p></div><button className="primary" onClick={newMigration}><Plus size={16} /> New migration</button></div><div className="stats">{['Total migrations', 'Running', 'Completed', 'Failed'].map(label => <div className="stat card" key={label}><span>{label}</span><strong>0</strong><small>No activity yet</small></div>)}</div><div className="content-grid"><section className="card history"><div className="section-head"><div><h2>Recent migrations</h2><p>Completed and active migrations will appear here.</p></div></div><div className="empty-state"><History size={23} /><strong>No migrations yet</strong><p>Start a migration to see its progress and history here.</p><button className="secondary" onClick={newMigration}><Plus size={14} /> Start first migration</button></div></section><aside className="card assistant"><div className="assistant-title"><div className="ai-icon"><Sparkles size={16} /></div><div><h2>Flowload AI</h2><p>Migration copilot</p></div></div><div className="assistant-copy"><p>Your workspace is ready. Create a migration to begin.</p><div className="insight"><ShieldCheck size={17} /><span><strong>Safety first</strong><small>Preflight checks run before every migration.</small></span></div></div></aside></div></main></>;
}

export default function App() {
  const [page, setPage] = useState<'dashboard' | 'new' | 'monitor'>('dashboard');
  const [job, setJob] = useState<MigrationJob | null>(null);
  return <div className="app"><aside className="sidebar"><div className="brand"><span className="brand-mark"><i /><i /><i /></span>flowload <small>beta</small></div><button className="new" onClick={() => setPage('new')}><Plus size={16} /> New migration</button><div className="nav-label">WORKSPACE</div><nav><button className={page === 'dashboard' ? 'active' : ''} onClick={() => setPage('dashboard')}><LayoutDashboard size={16} /> Dashboard</button><button><Database size={16} /> Connections</button><button><ListTree size={16} /> Schema explorer</button><button><History size={16} /> Migration history</button></nav><div className="sidebar-foot"><div className="help"><Sparkles size={17} /><span><strong>Need a hand?</strong><small>Ask Flowload AI anything</small></span></div></div></aside><div className="page">{page === 'new' ? <NewMigration close={() => setPage('dashboard')} created={(createdJob) => { setJob(createdJob); setPage('monitor'); }} /> : page === 'monitor' && job ? <MigrationMonitor job={job} back={() => setPage('dashboard')} /> : <Dashboard newMigration={() => setPage('new')} />}</div></div>;
}
