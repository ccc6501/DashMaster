<script lang="ts">
  import { onMount } from 'svelte';

  type Device = {
    hostname: string;
    slot_index: number;
    http_port: number;
    admin_port: number;
    mqtt_topic: string;
    status: string;
    profile?: string | null;
    last_seen?: string | null;
  };

  let devices: Device[] = [];
  let error: string | null = null;

  async function fetchDevices() {
    try {
      const response = await fetch('/api/devices');
      if (!response.ok) {
        throw new Error(`Failed to load devices (${response.status})`);
      }
      devices = await response.json();
    } catch (err) {
      error = (err as Error).message;
    }
  }

  function handleEvent(eventName: string, payload: Record<string, unknown>) {
    switch (eventName) {
      case 'device.claimed': {
        const hostname = payload.hostname as string;
        const existing = devices.find((device) => device.hostname === hostname);
        if (existing) {
          existing.status = 'claimed';
          existing.profile = (payload.profile as string) ?? existing.profile;
        }
        break;
      }
      case 'device.released': {
        const hostname = payload.hostname as string;
        const existing = devices.find((device) => device.hostname === hostname);
        if (existing) {
          existing.status = 'unclaimed';
          existing.profile = null;
        }
        break;
      }
      case 'config.uploaded': {
        const hostname = payload.hostname as string;
        const existing = devices.find((device) => device.hostname === hostname);
        if (existing) {
          existing.status = 'configured';
        }
        break;
      }
      default:
        break;
    }
    devices = [...devices];
  }

  onMount(() => {
    fetchDevices();
    const source = new EventSource('/api/stream');
    const handler = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data);
        handleEvent(event.type, payload as Record<string, unknown>);
      } catch (err) {
        console.warn('Failed to parse SSE payload', err);
      }
    };
    for (const eventName of ['device.claimed', 'device.released', 'config.uploaded']) {
      source.addEventListener(eventName, handler);
    }
    return () => source.close();
  });
</script>

{#if error}
  <p class="error">{error}</p>
{:else}
  <section class="devices-grid">
    {#each devices as device}
      <article class={`device-card status-${device.status}`}>
        <header>
          <h2>{device.hostname}</h2>
          <span>{device.status}</span>
        </header>
        <dl>
          <div>
            <dt>Profile</dt>
            <dd>{device.profile ?? '—'}</dd>
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
      </article>
    {/each}
  </section>
{/if}

<style>
  .devices-grid {
    display: grid;
    gap: 1.5rem;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  }

  .device-card {
    border: 1px solid #333;
    border-radius: 0.75rem;
    padding: 1rem;
    background: #0f172a;
    color: #f8fafc;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.5rem;
  }

  h2 {
    font-size: 1.1rem;
    margin: 0;
  }

  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.25rem 0.5rem;
  }

  dt {
    font-weight: 600;
    color: #94a3b8;
  }

  dd {
    margin: 0;
  }

  .error {
    color: #f87171;
  }
</style>
