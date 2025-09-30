<script lang="ts">
  import { onMount } from 'svelte';
  import {
    listDevices,
    listSnapshots,
    rollbackDevice,
    uploadPack
  } from '$lib/api';
  import type { Device, Snapshot, UploadResponse } from '$lib/types';

  let devices: Device[] = [];
  let hostname = '';
  let files: File[] = [];
  let message: string | null = null;
  let error: string | null = null;
  let uploadResult: UploadResponse | null = null;
  let isSubmitting = false;
  let isDragging = false;
  let snapshotCache: Record<string, Snapshot[]> = {};
  let snapshotLoading: Record<string, boolean> = {};
  let busy = false;
  let fileInput: HTMLInputElement | null = null;

  async function loadDevices() {
    try {
      devices = await listDevices();
      error = null;
      if (!hostname && devices.length) {
        hostname = devices[0].hostname;
        ensureSnapshots(hostname);
      }
    } catch (err) {
      error = (err as Error).message;
    }
  }

  function handleFileInput(list: FileList | null) {
    files = list ? Array.from(list) : [];
  }

  function handleDragOver(event: DragEvent) {
    event.preventDefault();
    isDragging = true;
  }

  function handleDragLeave(event: DragEvent) {
    event.preventDefault();
    isDragging = false;
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault();
    isDragging = false;
    if (event.dataTransfer?.files?.length) {
      handleFileInput(event.dataTransfer.files);
    }
  }

  function handleKeyActivate(event: KeyboardEvent) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      fileInput?.click();
    }
  }

  async function ensureSnapshots(target: string) {
    if (snapshotCache[target] || snapshotLoading[target]) return;
    snapshotLoading = { ...snapshotLoading, [target]: true };
    try {
      snapshotCache = { ...snapshotCache, [target]: await listSnapshots(target) };
      error = null;
    } catch (err) {
      error = (err as Error).message;
    } finally {
      const { [target]: _, ...rest } = snapshotLoading;
      snapshotLoading = rest;
    }
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!hostname) {
      message = 'Select a device.';
      return;
    }
    if (!files.length) {
      message = 'Drop a config pack before uploading.';
      return;
    }
    isSubmitting = true;
    message = null;
    error = null;
    try {
      uploadResult = await uploadPack(hostname, files);
      message = `Upload applied to ${uploadResult.device}`;
      ensureSnapshots(hostname);
    } catch (err) {
      error = (err as Error).message;
      uploadResult = null;
    } finally {
      isSubmitting = false;
    }
  }

  async function performRollback(snapshot: string) {
    if (!hostname) return;
    busy = true;
    message = null;
    error = null;
    try {
      const result = await rollbackDevice(hostname, snapshot);
      message = `Rolled back ${hostname} to ${result.rollback}`;
      uploadResult = {
        device: result.device,
        diff: result.diff,
        hashes: result.hashes,
        snapshot: result.rollback
      };
      snapshotCache = { ...snapshotCache, [hostname]: await listSnapshots(hostname) };
    } catch (err) {
      error = (err as Error).message;
    } finally {
      busy = false;
    }
  }

  function formatTimestamp(value?: string) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
  }

  function diffEntries() {
    if (!uploadResult) return [];
    return Object.entries(uploadResult.diff).map(([key, value]) => ({ key, value }));
  }

  onMount(loadDevices);
</script>

<section class="deploy">
  <form on:submit|preventDefault={submit} class="deploy-form">
    <label>
      Target Device
      <select
        bind:value={hostname}
        on:change={(event) => {
          const value = (event.currentTarget as HTMLSelectElement).value;
          hostname = value;
          ensureSnapshots(value);
        }}
      >
        {#if !devices.length}
          <option value="">Loading…</option>
        {:else}
          {#each devices as device}
            <option value={device.hostname}>{device.hostname}</option>
          {/each}
        {/if}
      </select>
    </label>

    <div
      class={`dropzone ${isDragging ? 'dragging' : ''}`}
      role="button"
      tabindex="0"
      aria-label="Upload configuration pack"
      on:dragover={handleDragOver}
      on:dragleave={handleDragLeave}
      on:drop={handleDrop}
      on:keydown={handleKeyActivate}
    >
      <p>Drag & drop config pack files here</p>
      <p>or</p>
      <label class="file-input">
        Browse
        <input
          bind:this={fileInput}
          type="file"
          multiple
          on:change={(event) => handleFileInput(event.currentTarget?.files ?? null)}
        />
      </label>
      {#if files.length}
        <ul>
          {#each files as file}
            <li>{file.name}</li>
          {/each}
        </ul>
      {/if}
    </div>

    <button type="submit" disabled={isSubmitting}>Upload</button>
  </form>

  <section class="status">
    {#if message}
      <p class="message success">{message}</p>
    {/if}
    {#if error}
      <p class="message error">{error}</p>
    {/if}

    {#if uploadResult}
      <div class="result">
        <h2>Diff Preview</h2>
        <ul>
          {#each diffEntries() as entry}
            <li class={entry.value ? 'changed' : 'unchanged'}>
              <strong>{entry.key}</strong>
              <span>{entry.value ? 'Changed' : 'Unchanged'}</span>
            </li>
          {/each}
        </ul>
        <h3>Hashes</h3>
        <ul class="hashes">
          {#each Object.entries(uploadResult.hashes) as [key, value]}
            <li><strong>{key}:</strong> {value ?? '—'}</li>
          {/each}
        </ul>
        <p><strong>Snapshot:</strong> {uploadResult.snapshot ?? '—'}</p>
      </div>
    {/if}

    <div class="snapshots">
      <h2>Snapshots</h2>
      {#if hostname}
        {#if snapshotLoading[hostname]}
          <p>Loading snapshots…</p>
        {:else if snapshotCache[hostname]?.length}
          <ul>
            {#each snapshotCache[hostname] as snapshot}
              <li>
                <div>
                  <strong>{snapshot.name}</strong>
                  <span>{formatTimestamp(snapshot.created_at)}</span>
                </div>
                <button disabled={busy} on:click={() => performRollback(snapshot.name)}>Restore</button>
              </li>
            {/each}
          </ul>
        {:else}
          <p>No snapshots available.</p>
        {/if}
      {:else}
        <p>Select a device to review snapshots.</p>
      {/if}
    </div>
  </section>
</section>

<style>
  .deploy {
    display: grid;
    gap: 2rem;
    grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  }

  .deploy-form {
    display: grid;
    gap: 1.5rem;
    padding: 1.5rem;
    border: 1px solid #1e293b;
    border-radius: 0.75rem;
    background: #0f172a;
  }

  label {
    display: grid;
    gap: 0.5rem;
    font-weight: 600;
    color: #94a3b8;
  }

  select,
  input[type='file'] {
    font: inherit;
  }

  select {
    padding: 0.6rem;
    border-radius: 0.5rem;
    border: 1px solid #334155;
    background: #020617;
    color: #e2e8f0;
  }

  .dropzone {
    border: 2px dashed #334155;
    border-radius: 0.75rem;
    padding: 2rem;
    text-align: center;
    display: grid;
    gap: 0.5rem;
    color: #94a3b8;
  }

  .dropzone.dragging {
    border-color: #38bdf8;
    background: rgba(56, 189, 248, 0.1);
  }

  .dropzone ul {
    list-style: none;
    padding: 0;
    margin: 1rem 0 0;
    color: #e2e8f0;
    text-align: left;
  }

  .file-input {
    display: inline-grid;
    gap: 0.25rem;
    justify-items: center;
    padding: 0.5rem 1rem;
    border-radius: 999px;
    background: #1e293b;
    color: #e2e8f0;
    cursor: pointer;
  }

  .file-input input {
    display: none;
  }

  button {
    padding: 0.6rem 1rem;
    border: none;
    border-radius: 0.5rem;
    background: #38bdf8;
    color: #0f172a;
    font-weight: 600;
    cursor: pointer;
  }

  button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .status {
    display: grid;
    gap: 1.5rem;
  }

  .message {
    padding: 0.75rem 1rem;
    border-radius: 0.5rem;
  }

  .message.success {
    background: rgba(34, 197, 94, 0.2);
    color: #4ade80;
  }

  .message.error {
    background: rgba(248, 113, 113, 0.15);
    color: #fca5a5;
  }

  .result {
    border: 1px solid #1e293b;
    border-radius: 0.75rem;
    padding: 1.25rem;
    background: #111c32;
    display: grid;
    gap: 1rem;
  }

  .result ul {
    list-style: none;
    padding: 0;
    margin: 0;
    display: grid;
    gap: 0.5rem;
  }

  .result li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0.75rem;
    border-radius: 0.5rem;
    background: rgba(15, 23, 42, 0.75);
  }

  .result li.changed {
    border-left: 3px solid #38bdf8;
  }

  .result li.unchanged {
    border-left: 3px solid #1e293b;
  }

  .hashes {
    font-family: 'Fira Code', 'SFMono-Regular', ui-monospace, monospace;
    font-size: 0.85rem;
  }

  .snapshots {
    border: 1px solid #1e293b;
    border-radius: 0.75rem;
    padding: 1.25rem;
    background: #0f172a;
    display: grid;
    gap: 1rem;
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
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: rgba(15, 23, 42, 0.8);
    border-radius: 0.5rem;
  }

  .snapshots span {
    display: block;
    color: #94a3b8;
    font-size: 0.8rem;
  }

  @media (max-width: 960px) {
    .deploy {
      grid-template-columns: 1fr;
    }
  }
</style>
