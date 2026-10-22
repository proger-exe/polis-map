export type User = {
  id: number;
  username: string;
  role: 'admin' | 'mapper' | 'leader' | 'player' | string;
  telegram_id?: string | null;
};

export type Point = { x: number; y: number };

export type State = {
  id: number;
  name: string;
  short_name: string;
  description: string;
  color: string;
  leader_id: number;
  capital_point: Point;
  government_type: string;
  status: string;
};

export type Territory = {
  id: number;
  name: string;
  state_id: number | null;
  type: string;
  status: string;
  color: string;
  points: Point[];
  area_size: number;
  version: number;
};

export type MapPayload = {
  image_url: string;
  width: number;
  height: number;
  states: State[];
  territories: Territory[];
  objects: unknown[];
};

export type AdminBootstrap = {
  users: User[];
  states: State[];
};

export type PoliticalAction = {
  id: number;
  type: string;
  actor_state_id: number | null;
  target_state_id: number | null;
  territory_id: number | null;
  created_by: number;
  status: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type AuditLog = {
  id: number;
  user_id: number | null;
  action_type: string;
  entity_type: string;
  entity_id: number | null;
  reason: string;
  created_at: string;
};

export type StateLinkResult = {
  code: string;
  user: User;
  state: State;
};

export type MapStateResult = {
  state: State;
  territory: Territory;
};
