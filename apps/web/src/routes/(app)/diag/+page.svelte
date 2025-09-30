<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { listDevices, subscribeToCompanionEvents } from '$lib/api';
  import type { CompanionEvent, Device } from '$lib/types';

  let devices: Device[] = [];
  let connectionState: 'connecting' | 'open' | 'error' = 'connecting';
  let lastEventAt: string | null = null;
  let lastPollAt: string | null = null;
  let error: string | null = null;
  let eventLog: {
    type: string;
    hostname: string;
    ts: string;
    summary: string;
  }[] = [];
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  async function pollDevices() {
    try {
      devices = await listDevices();
      lastPollAt = new Date().toISOString();
      error = null;
    } catch (err) {
      error = (err as Error).message;
    }
  }

  function pushEvent(event: CompanionEvent) {
    const ts = 'ts' in event.payload && event.payload.ts ? event.payload.ts : new Date().toISOString();
    lastEventAt = ts;
    const summary = (() => {
      switch (event.type) {
        case 'device.claimed':
          return `${event.payload.hostname} claimed`;
        case 'device.released':
          return `${event.payload.hostname} released`;
        case 'config.uploaded':
          return `${event.payload.hostname} uploaded`;
        case 'config.rollback':
          return `${event.payload.hostname} rolled back to ${event.payload.snapshot}`;
      }
    })();

    eventLog = [{ type: event.type, hostname: event.payload.hostname, ts, summary }, ...eventLog].slice(0, 20);
  }

  function formatTimestamp(value: string | null) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
  }

  function statusCounts() {
    return devices.reduce(
      (acc, device) => {
        acc.total += 1;
        acc[device.status] = (acc[device.status] ?? 0) + 1;
        return acc;
      },
      { total: 0 } as Record<string, number>
    );
  }

  onMount(() => {
    pollDevices();
    pollTimer = setInterval(pollDevices, 10000);
    const unsubscribe = subscribeToCompanionEvents(
      ['device.claimed', 'device.released', 'config.uploaded', 'config.rollback'],
      (event) => {
        pushEvent(event);
        pollDevices();
      },
      {
        onOpen: () => {
          connectionState = 'open';
          error = null;
        },
        onError: () => {
          connectionState = 'error';
        }
      }
    );
    onDestroy(() => {
      if (pollTimer) clearInterval(pollTimer);
      unsubscribe();
    });
  });
</script>

<section class="diag">
  <header>
    <h1>Diagnostics</h1>
    <div class={`connection state-${connectionState}`}>
      SSE: {connectionState}
    </div>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <section class="grid">
    <article class="card">
      <h2>Fleet Status</h2>
      <ul>
        {#each Object.entries(statusCounts()) as [key, value]}
          <li>
            <strong>{key}</strong>
            <span>{value}</span>
          </li>
        {/each}
      </ul>
      <p class="meta">Last poll · {formatTimestamp(lastPollAt)}</p>
    </article>

    <article class="card">
      <h2>Latest Event</h2>
      <p class="meta">{formatTimestamp(lastEventAt)}</p>
      {#if eventLog.length}
        <p>{eventLog[0].summary}</p>
      {:else}
        <p>No events yet.</p>
      {/if}
    </article>
  </section>

  <section class="events card">
    <h2>Event Stream</h2>
    <ul>
      {#each eventLog as entry}
        <li>
          <div>
            <span class="type">{entry.type}</span>
            <strong>{entry.hostname}</strong>
          </div>
          <span class="time">{formatTimestamp(entry.ts)}</span>
          <p>{entry.summary}</p>
        </li>
      {/each}
    </ul>
  </section>

  <section class="devices card">
    <h2>Device Snapshot</h2>
    <table>
      <thead>
        <tr>
          <th>Hostname</th>
          <th>Status</th>
          <th>Profile</th>
          <th>Last Upload</th>
        </tr>
      </thead>
      <tbody>
        {#each devices as device}
          <tr>
            <td>{device.hostname}</td>
            <td>{device.status}</td>
            <td>{device.profile ?? '—'}</td>
            <td>{formatTimestamp(device.last_upload_at ?? null)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </section>
</section>

<style>
  .diag {
    display: grid;
    gap: 1.5rem;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .connection {
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    font-size: 0.85rem;
    text-transform: capitalize;
    background: #1e293b;
    color: #e2e8f0;
  }

  .connection.state-open {
    background: rgba(34, 197, 94, 0.2);
    color: #4ade80;
  }

  .connection.state-error {
    background: rgba(248, 113, 113, 0.2);
    color: #fca5a5;
  }

  .error {
    color: #f87171;
  }

  .grid {
    display: grid;
    gap: 1.5rem;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  }

  .card {
    border: 1px solid #1e293b;
    border-radius: 0.75rem;
    padding: 1.25rem;
    background: #0f172a;
    display: grid;
    gap: 1rem;
  }

  .card ul {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .card li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.4rem 0;
    border-bottom: 1px solid rgba(15, 23, 42, 0.8);
  }

  .card li:last-child {
    border-bottom: none;
  }

  .meta {
    color: #94a3b8;
    font-size: 0.85rem;
  }

  .events ul {
    display: grid;
    gap: 0.75rem;
  }

  .events li {
    display: grid;
    gap: 0.25rem;
    background: rgba(15, 23, 42, 0.75);
    padding: 0.75rem;
    border-radius: 0.5rem;
  }

  .type {
    font-family: 'Fira Code', 'SFMono-Regular', ui-monospace, monospace;
    color: #60a5fa;
  }

  .time {
    color: #94a3b8;
    font-size: 0.85rem;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.95rem;
  }

  th,
  td {
    padding: 0.6rem;
    text-align: left;
    border-bottom: 1px solid rgba(15, 23, 42, 0.6);
  }

  tbody tr:hover {
    background: rgba(30, 41, 59, 0.3);
  }

  @media (max-width: 768px) {
    table {
      font-size: 0.85rem;
    }
  }
</style>
