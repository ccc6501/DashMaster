<script lang="ts">
  let hostname = '';
  let files: FileList | null = null;
  let message: string | null = null;

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!hostname || !files) {
      message = 'Select a device and at least one file.';
      return;
    }
    const formData = new FormData();
    for (const file of Array.from(files)) {
      formData.append(file.name, file);
    }
    try {
      const response = await fetch(`/api/upload/${hostname}`, {
        method: 'POST',
        body: formData
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail ?? 'Upload failed');
      }
      message = 'Upload submitted';
    } catch (err) {
      message = (err as Error).message;
    }
  }
</script>

<form on:submit|preventDefault={submit} class="deploy-form">
  <label>
    Hostname
    <input bind:value={hostname} placeholder="esp-000" />
  </label>
  <label>
    Config Pack
    <input type="file" multiple on:change={(event) => (files = event.currentTarget?.files ?? null)} />
  </label>
  <button type="submit">Upload</button>
</form>

{#if message}
  <p>{message}</p>
{/if}

<style>
  .deploy-form {
    display: grid;
    gap: 1rem;
    max-width: 420px;
  }

  label {
    display: grid;
    gap: 0.25rem;
  }

  input {
    padding: 0.5rem;
    border-radius: 0.5rem;
    border: 1px solid #475569;
  }

  button {
    padding: 0.6rem 1rem;
    background: #38bdf8;
    border: none;
    border-radius: 0.5rem;
    color: #0f172a;
    font-weight: 600;
    cursor: pointer;
  }
</style>
