import type { CompanionEvent, CompanionEventName, Device, RollbackResponse, Snapshot, UploadResponse } from './types';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    const message = typeof detail.detail === 'string' ? detail.detail : response.statusText;
    throw new Error(message || 'Request failed');
  }
  return (await response.json()) as T;
}

export async function listDevices(): Promise<Device[]> {
  const response = await fetch('/api/devices');
  return handleResponse<Device[]>(response);
}

export async function listSnapshots(hostname: string): Promise<Snapshot[]> {
  const response = await fetch(`/api/upload/${hostname}/snapshots`);
  return handleResponse<Snapshot[]>(response);
}

export async function identifyDevice(hostname: string, minutes = 5): Promise<void> {
  const response = await fetch(`/api/devices/${hostname}/identify?minutes=${minutes}`, {
    method: 'POST'
  });
  await handleResponse(response);
}

export async function rebootDevice(hostname: string): Promise<void> {
  const response = await fetch(`/api/devices/${hostname}/reboot`, { method: 'POST' });
  await handleResponse(response);
}

export async function factoryResetDevice(hostname: string): Promise<void> {
  const response = await fetch(`/api/devices/${hostname}/factory_reset`, { method: 'POST' });
  await handleResponse(response);
}

export async function rollbackDevice(hostname: string, snapshot?: string, actor?: string): Promise<RollbackResponse> {
  const response = await fetch(`/api/upload/${hostname}/rollback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ snapshot, actor })
  });
  return handleResponse<RollbackResponse>(response);
}

export async function uploadPack(hostname: string, files: File[]): Promise<UploadResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append(file.name, file);
  }
  const response = await fetch(`/api/upload/${hostname}`, {
    method: 'POST',
    body: formData
  });
  return handleResponse<UploadResponse>(response);
}

export function subscribeToCompanionEvents(
  events: CompanionEventName[],
  handler: (event: CompanionEvent) => void,
  options?: { onOpen?: () => void; onError?: (event: Event) => void },
): () => void {
  const source = new EventSource('/api/stream');
  if (options?.onOpen) {
    source.onopen = options.onOpen;
  }
  if (options?.onError) {
    source.onerror = options.onError;
  }
  const listener = (event: MessageEvent<string>) => {
    try {
      const payload = JSON.parse(event.data);
      handler({ type: event.type as CompanionEventName, payload });
    } catch (error) {
      console.warn('Failed to parse event payload', error);
    }
  };

  for (const eventName of events) {
    source.addEventListener(eventName, listener);
  }

  return () => {
    for (const eventName of events) {
      source.removeEventListener(eventName, listener);
    }
    source.close();
  };
}
