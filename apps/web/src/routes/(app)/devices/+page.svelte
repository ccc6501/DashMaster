<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import {
    factoryResetDevice,
    identifyDevice,
    listDevices,
    listSnapshots,
    rebootDevice,
    rollbackDevice,
    subscribeToCompanionEvents
  } from '$lib/api';
  import type { CompanionEvent, ConfigDiff, Device, Snapshot } from '$lib/types';

  let devices: Device[] = [];
  let error: string | null = null;
  let busyHosts = new Set<string>();
  let expandedHosts = new Set<string>();
  let snapshotCache: Record<string, Snapshot[]> = {};
  let snapshotLoading: Record<string, boolean> = {};
  let eventState: Record<
    string,
    { type: string; diff: ConfigDiff; snapshot?: string | null; actor?: string | null; ts?: string }
  > = {};

  function setBusy(hostname: string, value: boolean) {
    const updated = new Set(busyHosts);
    if (value) {
      updated.add(hostname);
    } else {
      updated.delete(hostname);
    }
    busyHosts = updated;
  }

  function toggleExpanded(hostname: string) {
    const updated = new Set(expandedHosts);
    if (updated.has(hostname)) {
      updated.delete(hostname);
    } else {
      updated.add(hostname);
      if (!snapshotCache[hostname] && !snapshotLoading[hostname]) {
        loadSnapshots(hostname);
      }
    }
    expandedHosts = updated;
  }

  async function loadDevices() {
    try {
      devices = await listDevices();
      error = null;
    } catch (err) {
      error = (err as Error).message;
    }
  }

  async function loadSnapshots(hostname: string) {
    snapshotLoading = { ...snapshotLoading, [hostname]: true };
    try {
      snapshotCache = { ...snapshotCache, [hostname]: await listSnapshots(hostname) };
      error = null;
    } catch (err) {
      error = (err as Error).message;
    } finally {
      const { [hostname]: _, ...rest } = snapshotLoading;
      snapshotLoading = rest;
    }
  }

  function updateDevice(hostname: string, updater: (device: Device) => void) {
    devices = devices.map((device) => {
      if (device.hostname === hostname) {
        const copy: Device = {
          ...device,
          hashes: { ...device.hashes },
          snapshots: [...device.snapshots]
        };
        updater(copy);
        return copy;
      }
      return device;
    });
  }

  function buildEventState(event: CompanionEvent) {
    const base = {
      type: event.type,
      diff: undefined as ConfigDiff | undefined,
      snapshot: undefined as string | null | undefined,
      actor: 'actor' in event.payload ? event.payload.actor ?? undefined : undefined,
      ts: 'ts' in event.payload && event.payload.ts ? event.payload.ts : new Date().toISOString()
    };
    if (event.type === 'config.uploaded' || event.type === 'config.rollback') {
      base.diff = event.payload.diff;
      if ('snapshot' in event.payload) {
        base.snapshot = event.payload.snapshot ?? null;
      }
    }
    return base;
  }

  function handleRealtime(event: CompanionEvent) {
    const hostname = event.payload.hostname;
    switch (event.type) {
      case 'device.claimed':
        updateDevice(hostname, (device) => {
          device.status = 'claimed';
          device.profile = event.payload.profile ?? device.profile ?? null;
        });
        break;
      case 'device.released':
        updateDevice(hostname, (device) => {
          device.status = 'unclaimed';
          device.profile = null;
        });
        break;
      case 'config.uploaded':
        updateDevice(hostname, (device) => {
          device.status = 'configured';
          device.hashes = event.payload.hashes;
          device.last_upload_at = event.payload.ts ?? new Date().toISOString();
          if (event.payload.snapshot) {
            const unique = new Set([...device.snapshots, event.payload.snapshot]);
            device.snapshots = Array.from(unique).sort();
          }
        });
        if (expandedHosts.has(hostname)) {
          loadSnapshots(hostname);
        }
        break;
      case 'config.rollback':
        updateDevice(hostname, (device) => {
          device.status = 'configured';
          device.hashes = event.payload.hashes;
          device.last_upload_at = event.payload.ts ?? new Date().toISOString();
          const unique = new Set([...device.snapshots, event.payload.snapshot]);
          device.snapshots = Array.from(unique).sort();
        });
        if (expandedHosts.has(hostname)) {
          loadSnapshots(hostname);
        }
        break;
    }
    eventState = { ...eventState, [hostname]: buildEventState(event) };
  }

  async function runAction(hostname: string, action: () => Promise<void>) {
    setBusy(hostname, true);
    try {
      await action();
      error = null;
    } catch (err) {
      error = (err as Error).message;
    } finally {
      setBusy(hostname, false);
    }
  }

  async function runRollback(hostname: string, snapshot?: string) {
    setBusy(hostname, true);
    try {
      const response = await rollbackDevice(hostname, snapshot);
      updateDevice(hostname, (device) => {
        device.hashes = response.hashes;
        device.last_upload_at = new Date().toISOString();
      });
      error = null;
      if (expandedHosts.has(hostname)) {
        loadSnapshots(hostname);
      }
    } catch (err) {
      error = (err as Error).message;
    } finally {
      setBusy(hostname, false);
    }
  }

  function formatTimestamp(value?: string | null) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
  }

  function diffSummary(diff: ConfigDiff | undefined) {
    if (!diff) return '—';
    const changed = Object.entries(diff)
      .filter(([, value]) => value)
      .map(([key]) => key.replace(/_/g, ' '));
    return changed.length ? changed.join(', ') : 'No changes';
  }

  onMount(() => {
    loadDevices();
    const unsubscribe = subscribeToCompanionEvents(
      ['device.claimed', 'device.released', 'config.uploaded', 'config.rollback'],
      handleRealtime
    );
    onDestroy(unsubscribe);
  });
</script>

{#if error}
  <p class="error">{error}</p>
{/if}

<section class="devices-grid">
  {#each devices as device}
    <article class={`device-card status-${device.status}`}>
      <header>
        <div>
          <h2>{device.hostname}</h2>
          <p class="slot">Slot #{device.slot_index}</p>
        </div>
        <span class={`status-pill status-${device.status}`}>{device.status}</span>
      </header>

      <dl class="meta">
        <div>
          <dt>Profile</dt>
          <dd>{device.profile ?? '—'}</dd>
        </div>
        <div>
          <dt>Last Upload</dt>
          <dd>{formatTimestamp(device.last_upload_at)}</dd>
        </div>
        <div>
          <dt>Last Seen</dt>
          <dd>{formatTimestamp(device.last_seen)}</dd>
        </div>
        <div>
          <dt>HTTP</dt>
          <dd>{device.http_port}</dd>
        </div>
        <div>
          <dt>Admin</dt>
          <dd>{device.admin_port}</dd>
        </div>
        <div>
          <dt>MQTT</dt>
          <dd>{device.mqtt_topic}</dd>
        </div>
      </dl>

      <div class="actions">
        <button on:click={() => runAction(device.hostname, () => identifyDevice(device.hostname))} disabled={busyHosts.has(device.hostname)}>
          Identify
        </button>
        <button on:click={() => runAction(device.hostname, () => rebootDevice(device.hostname))} disabled={busyHosts.has(device.hostname)}>
          Reboot
        </button>
        <button on:click={() => runAction(device.hostname, () => factoryResetDevice(device.hostname))} disabled={busyHosts.has(device.hostname)}>
          Factory Reset
        </button>
        <button class="secondary" on:click={() => runRollback(device.hostname)} disabled={busyHosts.has(device.hostname)}>
          Rollback Latest
        </button>
      </div>

      <section class="hashes">
        <h3>Hashes</h3>
        <ul>
          {#each Object.entries(device.hashes) as [key, value]}
            <li><strong>{key}:</strong> {value ?? '—'}</li>
          {/each}
        </ul>
      </section>

      <section class="events">
        <h3>Last Event</h3>
        {#if eventState[device.hostname]}
          <p>
            <span class="event-type">{eventState[device.hostname].type}</span>
            · {formatTimestamp(eventState[device.hostname].ts)}
          </p>
          <p><strong>Snapshot:</strong> {eventState[device.hostname].snapshot ?? '—'}</p>
          <p><strong>Actor:</strong> {eventState[device.hostname].actor ?? '—'}</p>
          <p><strong>Diff:</strong> {diffSummary(eventState[device.hostname].diff)}</p>
        {:else}
          <p>Waiting for events…</p>
        {/if}
      </section>

      <section class="snapshots">
        <button class="link" on:click={() => toggleExpanded(device.hostname)}>
          {expandedHosts.has(device.hostname) ? 'Hide snapshots' : 'Show snapshots'}
        </button>
        {#if expandedHosts.has(device.hostname)}
          {#if snapshotLoading[device.hostname]}
            <p>Loading…</p>
          {:else if snapshotCache[device.hostname]?.length}
            <ul>
              {#each snapshotCache[device.hostname] as snapshot}
                <li>
                  <div>
                    <strong>{snapshot.name}</strong>
                    <span>{formatTimestamp(snapshot.created_at)}</span>
                  </div>
                  <button
                    class="secondary"
                    on:click={() => runRollback(device.hostname, snapshot.name)}
                    disabled={busyHosts.has(device.hostname)}
                  >
                    Restore
                  </button>
                </li>
              {/each}
            </ul>
          {:else}
            <p>No snapshots available.</p>
          {/if}
        {/if}
      </section>
    </article>
  {/each}
</section>

<style>
  .error {
    color: #f87171;
    margin-bottom: 1rem;
  }

  .devices-grid {
    display: grid;
    gap: 1.5rem;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  }

  .device-card {
    border: 1px solid #1e293b;
    border-radius: 0.75rem;
    padding: 1.25rem;
    background: #0f172a;
    color: #e2e8f0;
    display: grid;
    gap: 1rem;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
  }

  h2 {
    font-size: 1.2rem;
    margin: 0;
  }

  .slot {
    margin: 0;
    color: #94a3b8;
    font-size: 0.85rem;
  }

  .status-pill {
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.8rem;
    text-transform: capitalize;
    background: #1e293b;
  }

  .status-configured {
    background: rgba(34, 197, 94, 0.2);
    color: #22c55e;
  }

  .status-claimed {
    background: rgba(59, 130, 246, 0.2);
    color: #3b82f6;
  }

  .status-unclaimed {
    background: rgba(148, 163, 184, 0.2);
    color: #cbd5f5;
  }

  .meta {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.5rem 1rem;
  }

  dt {
    font-weight: 600;
    color: #94a3b8;
  }

  dd {
    margin: 0;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  button {
    padding: 0.5rem 0.9rem;
    border-radius: 0.5rem;
    border: none;
    background: #38bdf8;
    color: #0f172a;
    font-weight: 600;
    cursor: pointer;
  }

  button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  button.secondary {
    background: #1e293b;
    color: #e2e8f0;
  }

  button.link {
    background: none;
    padding: 0;
    color: #60a5fa;
    font-weight: 500;
  }

  .hashes ul {
    list-style: none;
    padding: 0;
    margin: 0;
    display: grid;
    gap: 0.25rem;
  }

  .hashes li {
    font-family: 'Fira Code', 'SFMono-Regular', ui-monospace, monospace;
    font-size: 0.8rem;
  }

  .events,
  .hashes,
  .snapshots {
    display: grid;
    gap: 0.5rem;
  }

  .events p,
  .snapshots p {
    margin: 0;
    font-size: 0.9rem;
  }

  .snapshots ul {
    list-style: none;
    padding: 0;
    margin: 0;
    display: grid;
    gap: 0.75rem;
  }

  .snapshots li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.5rem 0.75rem;
    background: rgba(30, 41, 59, 0.6);
    border-radius: 0.5rem;
  }

  .snapshots li div {
    display: grid;
    gap: 0.25rem;
  }

  .snapshots span {
    color: #94a3b8;
    font-size: 0.8rem;
  }

  .event-type {
    font-family: 'Fira Code', 'SFMono-Regular', ui-monospace, monospace;
    color: #60a5fa;
  }
</style>
