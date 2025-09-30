export type Device = {
  hostname: string;
  slot_index: number;
  http_port: number;
  admin_port: number;
  mqtt_topic: string;
  status: string;
  profile?: string | null;
  last_seen?: string | null;
  last_upload_at?: string | null;
  hashes: Record<string, string | null>;
  snapshots: string[];
};

export type ConfigDiff = Record<string, boolean>;

export type UploadResponse = {
  device: string;
  hashes: Record<string, string | null>;
  diff: ConfigDiff;
  snapshot: string | null;
};

export type RollbackResponse = {
  device: string;
  rollback: string;
  hashes: Record<string, string | null>;
  diff: ConfigDiff;
};

export type Snapshot = {
  name: string;
  created_at: string;
  files: string[];
  hashes: Record<string, string | null>;
};

export type CompanionEventName =
  | 'device.claimed'
  | 'device.released'
  | 'config.uploaded'
  | 'config.rollback';

export type CompanionEventPayloads = {
  'device.claimed': { hostname: string; slot_index: number; profile?: string | null };
  'device.released': { hostname: string };
  'config.uploaded': {
    hostname: string;
    hashes: Record<string, string | null>;
    diff: ConfigDiff;
    snapshot?: string | null;
    actor?: string | null;
    ts?: string;
  };
  'config.rollback': {
    hostname: string;
    snapshot: string;
    hashes: Record<string, string | null>;
    diff: ConfigDiff;
    actor?: string | null;
    ts?: string;
  };
};

export type CompanionEvent = {
  [K in CompanionEventName]: { type: K; payload: CompanionEventPayloads[K] }
}[CompanionEventName];
