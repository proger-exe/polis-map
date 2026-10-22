import type { AdminBootstrap, AuditLog, MapPayload, MapStateResult, PoliticalAction, State, StateLinkResult, Territory } from './types';

const jsonHeaders = (token?: string) => ({
  'Content-Type': 'application/json',
  ...(token ? { Authorization: `Bearer ${token}` } : {})
});

const authHeaders = (token: string) => ({ Authorization: `Bearer ${token}` });

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || response.statusText);
  }
  return response.json() as Promise<T>;
}

export async function bootstrap(): Promise<{ settings: { frontend_url: string; telegram_enabled: boolean } }> {
  return parse(await fetch('/api/bootstrap'));
}

export async function loadMap(): Promise<MapPayload> {
  return parse(await fetch('/api/map'));
}

export async function adminLogin(username: string, password: string): Promise<{ token: string; expires_at: string }> {
  return parse(await fetch('/api/admin/login', { method: 'POST', headers: jsonHeaders(), body: JSON.stringify({ username, password }) }));
}

export async function adminBootstrap(token: string): Promise<AdminBootstrap> {
  return parse(await fetch('/api/admin/bootstrap', { headers: authHeaders(token) }));
}

export async function loadAdminActions(token: string): Promise<PoliticalAction[]> {
  return parse(await fetch('/api/actions', { headers: authHeaders(token) }));
}

export async function loadAudit(token: string): Promise<AuditLog[]> {
  return parse(await fetch('/api/audit-log', { headers: authHeaders(token) }));
}

export async function saveTerritory(token: string, territory: Partial<Territory> & { points: { x: number; y: number }[] }) {
  const payload = {
    name: territory.name || 'Новая территория',
    state_id: territory.state_id ?? null,
    type: territory.type || 'neutral',
    status: territory.status || 'neutral',
    color: territory.color || '#8A9A5B',
    points: territory.points,
    reason: 'mapper edit'
  };
  const url = territory.id ? `/api/territories/${territory.id}` : '/api/territories';
  const method = territory.id ? 'PUT' : 'POST';
  return parse<Territory>(await fetch(url, { method, headers: jsonHeaders(token), body: JSON.stringify(payload) }));
}

export async function decideAction(token: string, actionId: number, decision: 'approve' | 'reject') {
  return parse<PoliticalAction>(
    await fetch(`/api/actions/${actionId}/${decision}`, {
      method: 'POST',
      headers: jsonHeaders(token),
      body: JSON.stringify({ reason: decision === 'approve' ? 'MVP approval' : 'MVP rejection' })
    })
  );
}

export async function uploadMap(token: string, file: File) {
  const form = new FormData();
  form.append('file', file);
  return parse(
    await fetch('/api/map/upload', {
      method: 'POST',
      headers: authHeaders(token),
      body: form
    })
  );
}

export async function createStateLinkCode(
  token: string,
  payload: { username: string; state_name: string; short_name: string; color: string; description: string; capital_point: { x: number; y: number } }
): Promise<StateLinkResult> {
  return parse(await fetch('/api/admin/states/link-code', { method: 'POST', headers: jsonHeaders(token), body: JSON.stringify(payload) }));
}

export async function createMapState(
  token: string,
  payload: { name: string; short_name: string; color: string; description: string; capital_point: { x: number; y: number } }
): Promise<MapStateResult> {
  return parse(await fetch('/api/admin/states/map-state', { method: 'POST', headers: jsonHeaders(token), body: JSON.stringify(payload) }));
}

export async function updateStateCapital(token: string, stateId: number, capitalPoint: { x: number; y: number }): Promise<State> {
  return parse(
    await fetch(`/api/admin/states/${stateId}/capital`, {
      method: 'PATCH',
      headers: jsonHeaders(token),
      body: JSON.stringify({ capital_point: capitalPoint })
    })
  );
}

export async function deleteState(token: string, stateId: number): Promise<{ state: unknown; territory_ids: number[] }> {
  return parse(await fetch(`/api/admin/states/${stateId}`, { method: 'DELETE', headers: authHeaders(token) }));
}
