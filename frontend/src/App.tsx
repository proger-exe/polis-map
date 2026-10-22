import { Check, Download, Eye, EyeOff, KeyRound, Magnet, MapPinned, Minus, Plus, RefreshCcw, RotateCcw, Trash2, Upload, X, ZoomIn, ZoomOut } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent, RefObject } from 'react';
import type { Stage as StageType } from 'konva/lib/Stage';
import { Circle, Group, Image as KonvaImage, Label, Layer, Line, Rect, Stage, Tag, Text } from 'react-konva';
import {
  adminBootstrap,
  adminLogin,
  createMapState,
  createStateLinkCode,
  deleteState,
  decideAction,
  loadAdminActions,
  loadAudit,
  loadMap,
  saveTerritory,
  updateStateCapital,
  uploadMap
} from './api';
import type { AuditLog, MapPayload, Point, PoliticalAction, State, StateLinkResult, Territory } from './types';

const publicMaxWidth = 1280;
const publicMaxHeight = 820;
type InteractionMode = 'select' | 'draw-territory' | 'pick-state-point' | 'create-map-state';

function useMapImage(url?: string) {
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  useEffect(() => {
    if (!url) return;
    const element = new window.Image();
    element.crossOrigin = 'anonymous';
    element.src = url;
    element.onload = () => setImage(element);
  }, [url]);
  return image;
}

function clamp(value: number) {
  return Math.max(0, Math.min(1, value));
}

function centroid(points: Point[]) {
  if (!points.length) return { x: 0, y: 0 };
  const total = points.reduce((acc, point) => ({ x: acc.x + point.x, y: acc.y + point.y }), { x: 0, y: 0 });
  return { x: total.x / points.length, y: total.y / points.length };
}

function stagePoints(points: Point[], width: number, height: number) {
  return points.flatMap((point) => [point.x * width, point.y * height]);
}

function useMapScale(map: MapPayload | null, maxWidth: number, maxHeight: number) {
  return useMemo(() => {
    if (!map) return { width: maxWidth, height: maxHeight };
    const scale = Math.min(maxWidth / map.width, maxHeight / map.height);
    return { width: map.width * scale, height: map.height * scale };
  }, [map, maxHeight, maxWidth]);
}

function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return { ref, size };
}

function MapCanvas({
  map,
  selectedId,
  selectedStateId,
  onSelect,
  onStateSelect,
  onStateMove,
  onLabelsToggle,
  editable,
  labels,
  draftPoints = [],
  onDraftClick,
  onPointDrag,
  selectedPointIndex,
  onPointSelect,
  statePointDraft,
  interactionMode = 'select',
  draftColor,
  fillParent,
  stageRef,
  maxWidth,
  maxHeight
}: {
  map: MapPayload | null;
  selectedId?: number | null;
  selectedStateId?: number | null;
  onSelect?: (id: number) => void;
  onStateSelect?: (id: number) => void;
  onStateMove?: (state: State, point: Point) => void;
  onLabelsToggle?: () => void;
  editable?: boolean;
  labels?: boolean;
  draftPoints?: Point[];
  onDraftClick?: (point: Point) => void;
  onPointDrag?: (territory: Territory, index: number, point: Point) => void;
  selectedPointIndex?: number | null;
  onPointSelect?: (index: number | null) => void;
  statePointDraft?: Point | null;
  interactionMode?: InteractionMode;
  draftColor?: string;
  fillParent?: boolean;
  stageRef?: RefObject<StageType>;
  maxWidth: number;
  maxHeight: number;
}) {
  const internalStageRef = useRef<StageType>(null);
  const activeStageRef = stageRef || internalStageRef;
  const { ref: shellRef, size: shellSize } = useElementSize<HTMLDivElement>();
  const viewport = {
    width: fillParent && shellSize.width > 0 ? shellSize.width : maxWidth,
    height: fillParent && shellSize.height > 0 ? shellSize.height : maxHeight
  };
  const image = useMapImage(map?.image_url);
  const size = useMapScale(map, viewport.width, viewport.height);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const downPointer = useRef<Point | null>(null);
  const didDrag = useRef(false);
  const clickWasDrag = useRef(false);
  const labelFontSize = Math.max(7, Math.min(13, 10 * Math.sqrt(zoom)));

  function setZoomAt(nextZoom: number, anchor?: Point) {
    const pointer = anchor || { x: size.width / 2, y: size.height / 2 };
    const clampedZoom = Math.max(0.5, Math.min(6, nextZoom));
    const mapPoint = { x: (pointer.x - pan.x) / zoom, y: (pointer.y - pan.y) / zoom };
    setZoom(clampedZoom);
    setPan({ x: pointer.x - mapPoint.x * clampedZoom, y: pointer.y - mapPoint.y * clampedZoom });
  }

  function resetView() {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }

  function normalizedPointer() {
    const stage = activeStageRef.current;
    const pointer = stage?.getPointerPosition();
    if (!stage || !pointer || !map) return null;
    return { x: clamp((pointer.x - pan.x) / zoom / size.width), y: clamp((pointer.y - pan.y) / zoom / size.height) };
  }

  function screenPoint(point: Point) {
    return { x: pan.x + point.x * size.width * zoom, y: pan.y + point.y * size.height * zoom };
  }

  return (
    <div className={`map-canvas-shell${fillParent ? ' fill-parent' : ''}`} ref={shellRef}>
      <div className="zoom-controls">
        <button onClick={() => setZoomAt(zoom + 0.35)} title="Приблизить"><ZoomIn size={15} /></button>
        <button onClick={() => setZoomAt(zoom - 0.35)} title="Отдалить"><ZoomOut size={15} /></button>
        <button onClick={resetView} title="Сбросить зум"><RotateCcw size={15} /></button>
        {onLabelsToggle && (
          <button onClick={onLabelsToggle} title={labels ? 'Убрать подписи' : 'Показать подписи'}>
            {labels ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        )}
        <span>{Math.round(zoom * 100)}%</span>
      </div>
      <Stage
        ref={activeStageRef}
        width={size.width}
        height={size.height}
        onWheel={(event) => {
          event.evt.preventDefault();
          activeStageRef.current?.setPointersPositions(event.evt);
          const pointer = activeStageRef.current?.getPointerPosition();
          const delta = event.evt.deltaY > 0 ? -0.25 : 0.25;
          setZoomAt(zoom + delta, pointer || undefined);
        }}
        onMouseDown={() => {
          const pointer = activeStageRef.current?.getPointerPosition();
          if (!pointer) return;
          downPointer.current = pointer;
          didDrag.current = false;
        }}
        onMouseMove={() => {
          const pointer = activeStageRef.current?.getPointerPosition();
          if (!pointer || !downPointer.current) return;
          const distance = Math.hypot(pointer.x - downPointer.current.x, pointer.y - downPointer.current.y);
          if (distance > 4) didDrag.current = true;
        }}
        onMouseUp={() => {
          clickWasDrag.current = didDrag.current;
          downPointer.current = null;
        }}
        onMouseLeave={() => {
          clickWasDrag.current = didDrag.current;
          downPointer.current = null;
        }}
        onClick={() => {
          if (clickWasDrag.current) {
            clickWasDrag.current = false;
            return;
          }
          const point = normalizedPointer();
          if (point && onDraftClick) onDraftClick(point);
        }}
      >
        <Layer>
          <Group x={pan.x} y={pan.y} scaleX={zoom} scaleY={zoom}>
            <Rect name="map-bg" width={size.width} height={size.height} fill="#cad6d4" />
            {image && <KonvaImage name="map-image" image={image} width={size.width} height={size.height} />}
            {map?.territories.map((territory) => {
              const isSelected = territory.id === selectedId;
              return (
                <Group
                  key={territory.id}
                  onClick={(event) => {
                    if (clickWasDrag.current) return;
                    if (interactionMode !== 'select') return;
                    event.cancelBubble = true;
                    onSelect?.(territory.id);
                  }}
                >
                  <Line
                    points={stagePoints(territory.points, size.width, size.height)}
                    closed
                    fill={territory.color}
                    opacity={isSelected ? 0.42 : 0.3}
                    stroke={isSelected ? '#fff8d8' : '#f4f0dc'}
                    strokeWidth={isSelected ? 4 / zoom : 2.5 / zoom}
                    shadowColor="#172226"
                    shadowOpacity={0.22}
                    shadowBlur={isSelected ? 8 / zoom : 3 / zoom}
                  />
                  {editable &&
                    isSelected &&
                    territory.points.map((point, index) => (
                      <Circle
                        name="vertex-handle"
                        key={`${territory.id}-${index}`}
                        x={point.x * size.width}
                        y={point.y * size.height}
                        radius={(selectedPointIndex === index ? 10 : 7) / zoom}
                        fill={selectedPointIndex === index ? '#d95d39' : '#fff8d8'}
                        stroke="#172226"
                        strokeWidth={2 / zoom}
                        draggable
                        onClick={(event) => {
                          event.cancelBubble = true;
                          onPointSelect?.(index);
                        }}
                        onDragStart={() => onPointSelect?.(index)}
                        onDragEnd={(event) =>
                          onPointDrag?.(territory, index, {
                            x: clamp(event.target.x() / size.width),
                            y: clamp(event.target.y() / size.height)
                          })
                        }
                      />
                    ))}
                </Group>
              );
            })}
            {draftPoints.length > 0 && (
              <Line points={stagePoints(draftPoints, size.width, size.height)} closed={draftPoints.length > 2} fill={draftColor || '#d95d39'} opacity={0.28} stroke="#fff8d8" strokeWidth={3 / zoom} />
            )}
            {draftPoints.map((point, index) => (
              <Circle key={index} x={point.x * size.width} y={point.y * size.height} radius={6 / zoom} fill={draftColor || '#d95d39'} stroke="#fff8d8" strokeWidth={2 / zoom} />
            ))}
          </Group>
          {labels &&
            map?.territories.map((territory) => {
              const labelPoint = screenPoint(centroid(territory.points));
              const labelWidth = Math.max(34, Math.min(180, territory.name.length * labelFontSize * 0.62 + 14));
              return (
                <Label key={`label-${territory.id}`} x={labelPoint.x} y={labelPoint.y} offsetX={labelWidth / 2} offsetY={labelFontSize + 6} listening={false}>
                  <Tag fill="rgba(244, 240, 220, 0.76)" stroke="#f4f0dc" strokeWidth={1} cornerRadius={4} />
                  <Text
                    text={territory.name}
                    width={labelWidth}
                    align="center"
                    padding={4}
                    fill="#172226"
                    fontFamily="IBM Plex Sans"
                    fontStyle="700"
                    fontSize={labelFontSize}
                  />
                </Label>
              );
            })}
          {map?.states.map((state) => {
            const point = screenPoint(state.capital_point);
            const isSelected = state.id === selectedStateId;
            return (
              <Group
                key={`state-${state.id}`}
                x={point.x}
                y={point.y}
                draggable={editable}
                onClick={(event) => {
                  if (clickWasDrag.current) return;
                  event.cancelBubble = true;
                  onStateSelect?.(state.id);
                }}
                onDragStart={() => {
                  didDrag.current = true;
                }}
                onDragEnd={(event) => {
                  onStateMove?.(state, {
                    x: clamp((event.target.x() - pan.x) / zoom / size.width),
                    y: clamp((event.target.y() - pan.y) / zoom / size.height)
                  });
                }}
              >
                <Circle radius={18} fill="rgba(255, 255, 255, 0.01)" />
                <Circle radius={isSelected ? 14 : 9} fill={state.color} opacity={0.94} shadowColor="#172226" shadowBlur={8} shadowOpacity={0.35} />
                <Text text={state.short_name} x={12} y={-11} fill="#172226" fontFamily="JetBrains Mono" fontStyle="800" fontSize={14} letterSpacing={0.4} shadowColor="#f8f4e8" shadowBlur={2} shadowOpacity={0.95} />
              </Group>
            );
          })}
          {statePointDraft && (() => {
            const point = screenPoint(statePointDraft);
            return (
              <Group x={point.x} y={point.y} listening={false}>
                <Circle radius={10} fill="#f2b84b" opacity={0.95} shadowColor="#172226" shadowBlur={7} shadowOpacity={0.28} />
                <Text text="новое" x={14} y={-11} fill="#172226" fontFamily="JetBrains Mono" fontStyle="800" fontSize={14} letterSpacing={0.4} shadowColor="#f8f4e8" shadowBlur={2} shadowOpacity={0.95} />
              </Group>
            );
          })()}
        </Layer>
      </Stage>
    </div>
  );
}

export function App() {
  return window.location.pathname.startsWith('/admin') ? <AdminApp /> : <PublicMap />;
}

function PublicMap() {
  const [map, setMap] = useState<MapPayload | null>(null);
  const [labels, setLabels] = useState(true);

  useEffect(() => {
    loadMap()
      .then((payload) => setMap(payload))
      .catch(() => setMap(null));
  }, []);

  return (
    <main className="public-map-page">
      <div className="public-map-frame">
        <MapCanvas
          map={map}
          labels={labels}
          onLabelsToggle={() => setLabels(!labels)}
          fillParent
          maxWidth={publicMaxWidth}
          maxHeight={publicMaxHeight}
        />
      </div>
    </main>
  );
}

function AdminApp() {
  const [token, setToken] = useState(() => localStorage.getItem('polis_admin_token') || '');
  const [login, setLogin] = useState({ username: 'admin', password: 'admin' });
  const [map, setMap] = useState<MapPayload | null>(null);
  const [states, setStates] = useState<State[]>([]);
  const [actions, setActions] = useState<PoliticalAction[]>([]);
  const [audit, setAudit] = useState<AuditLog[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedStateId, setSelectedStateId] = useState<number | null>(null);
  const [selectedPointIndex, setSelectedPointIndex] = useState<number | null>(null);
  const [draftPoints, setDraftPoints] = useState<Point[]>([]);
  const [drawMode, setDrawMode] = useState(false);
  const [statePointMode, setStatePointMode] = useState(false);
  const [statePoint, setStatePoint] = useState<Point | null>(null);
  const [mapStateMode, setMapStateMode] = useState(false);
  const [mapStateForm, setMapStateForm] = useState({ name: '', short_name: '', color: '#4A90E2', description: '' });
  const [labels, setLabels] = useState(true);
  const [status, setStatus] = useState('Админ-панель');
  const [linkForm, setLinkForm] = useState({ username: '', state_name: '', short_name: '', color: '#4A90E2', description: '' });
  const [lastLink, setLastLink] = useState<StateLinkResult | null>(null);
  const stageRef = useRef<StageType>(null);
  const selected = map?.territories.find((territory) => territory.id === selectedId) || null;
  const selectedState = states.find((state) => state.id === selectedStateId) || null;
  const interactionMode: InteractionMode = mapStateMode ? 'create-map-state' : statePointMode ? 'pick-state-point' : drawMode ? 'draw-territory' : 'select';

  async function refresh(authToken = token) {
    const [mapPayload, adminPayload, actionPayload, auditPayload] = await Promise.all([
      loadMap(),
      adminBootstrap(authToken),
      loadAdminActions(authToken),
      loadAudit(authToken)
    ]);
    setMap(mapPayload);
    setStates(adminPayload.states);
    setActions(actionPayload);
    setAudit(auditPayload);
    if (selectedId && !mapPayload.territories.some((territory) => territory.id === selectedId)) {
      setSelectedId(mapPayload.territories[0]?.id || null);
      setSelectedPointIndex(null);
    }
    if (!selectedId && mapPayload.territories[0]) setSelectedId(mapPayload.territories[0].id);
    if (selectedStateId && !adminPayload.states.some((state) => state.id === selectedStateId)) setSelectedStateId(null);
  }

  useEffect(() => {
    if (!token) return;
    refresh().catch((error) => {
      setStatus(error.message);
      localStorage.removeItem('polis_admin_token');
      setToken('');
    });
  }, [token]);

  async function submitLogin(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await adminLogin(login.username, login.password);
      localStorage.setItem('polis_admin_token', result.token);
      setToken(result.token);
      setStatus('Вход выполнен');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Ошибка входа');
    }
  }

  async function createLink(event: FormEvent) {
    event.preventDefault();
    if (!statePoint) {
      setStatus('Выберите точку государства на карте');
      return;
    }
    try {
      const result = await createStateLinkCode(token, { ...linkForm, capital_point: statePoint });
      setLastLink(result);
      setLinkForm({ username: '', state_name: '', short_name: '', color: '#4A90E2', description: '' });
      setStatePoint(null);
      setStatePointMode(false);
      await refresh();
      setStatus('Код привязки создан');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Ошибка кода');
    }
  }

  async function createStateAt(point: Point) {
    const name = mapStateForm.name.trim();
    if (!name) {
      setStatus('Введите название государства');
      setMapStateMode(false);
      return;
    }
    try {
      const result = await createMapState(token, {
        ...mapStateForm,
        name,
        short_name: mapStateForm.short_name.trim(),
        capital_point: point
      });
      setMapStateForm({ name: '', short_name: '', color: '#4A90E2', description: '' });
      setMapStateMode(false);
      setDrawMode(false);
      setStatePointMode(false);
      await refresh();
      setSelectedStateId(result.state.id);
      setSelectedId(result.territory.id);
      setSelectedPointIndex(0);
      setStatus('Государство создано с стартовой территорией');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Ошибка создания государства');
    }
  }

  async function saveSelected(points?: Point[], patch: Partial<Territory> = {}) {
    if (!selected) return;
    try {
      const state = states.find((item) => item.id === patch.state_id);
      await saveTerritory(token, { ...selected, ...patch, color: state?.color || patch.color || selected.color, points: points || selected.points });
      await refresh();
      setStatus('Территория сохранена');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Ошибка сохранения');
    }
  }

  async function moveStatePoint(state: State, point: Point) {
    try {
      await updateStateCapital(token, state.id, point);
      await refresh();
      setSelectedStateId(state.id);
      setStatus('Точка государства перемещена');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Ошибка перемещения точки');
      await refresh();
    }
  }

  async function addPointAfterSelected() {
    if (!selected || selectedPointIndex === null) {
      setStatus('Выберите вершину');
      return;
    }
    const current = selected.points[selectedPointIndex];
    const next = selected.points[(selectedPointIndex + 1) % selected.points.length];
    const midpoint = { x: (current.x + next.x) / 2, y: (current.y + next.y) / 2 };
    const points = [...selected.points.slice(0, selectedPointIndex + 1), midpoint, ...selected.points.slice(selectedPointIndex + 1)];
    await saveSelected(points);
    setSelectedPointIndex(selectedPointIndex + 1);
  }

  async function snapSelectedPoint() {
    if (!map || !selected || selectedPointIndex === null) {
      setStatus('Выберите вершину');
      return;
    }
    const current = selected.points[selectedPointIndex];
    let nearest: Point | null = null;
    let nearestDistance = Number.POSITIVE_INFINITY;
    for (const territory of map.territories) {
      if (territory.id === selected.id) continue;
      for (const point of territory.points) {
        const distance = Math.hypot(point.x - current.x, point.y - current.y);
        if (distance < nearestDistance) {
          nearest = point;
          nearestDistance = distance;
        }
      }
    }
    if (!nearest) {
      setStatus('Нет другой границы для магнита');
      return;
    }
    const points = selected.points.map((point, index) => (index === selectedPointIndex ? { x: nearest!.x, y: nearest!.y } : point));
    await saveSelected(points);
    setSelectedPointIndex(selectedPointIndex);
    setStatus('Точка примагничена к ближайшей границе');
  }

  async function deleteSelectedPoint() {
    if (!selected || selectedPointIndex === null) {
      setStatus('Выберите вершину');
      return;
    }
    if (selected.points.length <= 3) {
      setStatus('Нельзя удалить: минимум 3 точки');
      return;
    }
    const points = selected.points.filter((_, index) => index !== selectedPointIndex);
    await saveSelected(points);
    setSelectedPointIndex(Math.min(selectedPointIndex, points.length - 1));
  }

  async function removeState(state: State) {
    if (!window.confirm(`Удалить государство "${state.name}" и все его территории?`)) return;
    try {
      const result = await deleteState(token, state.id);
      const removedTerritoryIds = new Set(result.territory_ids);
      if (selectedStateId === state.id) setSelectedStateId(null);
      if (selectedId && removedTerritoryIds.has(selectedId)) setSelectedId(null);
      setSelectedPointIndex(null);
      setDraftPoints([]);
      setStatePoint(null);
      setDrawMode(false);
      setStatePointMode(false);
      setMapStateMode(false);
      await refresh();
      if (selectedStateId === state.id) setSelectedStateId(null);
      if (selectedId && removedTerritoryIds.has(selectedId)) setSelectedId(null);
      setSelectedPointIndex(null);
      setStatus(`Государство удалено, территорий: ${result.territory_ids.length}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Ошибка удаления');
    }
  }

  async function createDraft() {
    if (draftPoints.length < 3) {
      setStatus('Нужно минимум 3 точки');
      return;
    }
    try {
      const territory = await saveTerritory(token, {
        name: `Территория ${Date.now().toString().slice(-4)}`,
        state_id: selectedState?.id || null,
        type: selectedState ? 'state_core' : 'neutral',
        status: selectedState ? 'active' : 'neutral',
        color: selectedState?.color || '#9AA36B',
        points: draftPoints
      });
      setDraftPoints([]);
      setDrawMode(false);
      await refresh();
      setSelectedId(territory.id);
      setStatus(selectedState ? `Территория добавлена: ${selectedState.short_name}` : 'Нейтральный полигон создан');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Ошибка создания');
    }
  }

  function exportPng() {
    const uri = stageRef.current?.toDataURL({ pixelRatio: 2 });
    if (!uri) return;
    const link = document.createElement('a');
    link.download = `polis-map-${new Date().toISOString().slice(0, 10)}.png`;
    link.href = uri;
    link.click();
  }

  async function upload(file?: File) {
    if (!file) return;
    try {
      await uploadMap(token, file);
      await refresh();
      setStatus('Карта загружена с сервера');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Ошибка загрузки');
    }
  }

  if (!token) {
    return (
      <main className="admin-login-page">
        <form className="admin-login-card" onSubmit={submitLogin}>
          <span className="brand-mark">P</span>
          <h1>Admin</h1>
          <p>{status}</p>
          <input value={login.username} onChange={(event) => setLogin({ ...login, username: event.target.value })} placeholder="Логин" />
          <input value={login.password} onChange={(event) => setLogin({ ...login, password: event.target.value })} placeholder="Пароль" type="password" />
          <button>
            <KeyRound size={16} /> войти
          </button>
        </form>
      </main>
    );
  }

  return (
    <main className="admin-shell">
      <aside className="left-rail">
        <div className="brand-block">
          <span className="brand-mark">P</span>
          <div>
            <h1>Polis Admin</h1>
            <p>маппер и заявки</p>
          </div>
        </div>

        <section className="panel">
          <label>Карта</label>
          <div className="tool-grid">
            <button className={drawMode ? 'active' : ''} onClick={() => { setDrawMode(!drawMode); setStatePointMode(false); setMapStateMode(false); }} title="Создать полигон">
              <Plus size={17} />
            </button>
            <button onClick={createDraft} title="Сохранить полигон">
              <Check size={17} />
            </button>
            <button onClick={() => setDraftPoints([])} title="Очистить черновик">
              <X size={17} />
            </button>
            <button onClick={exportPng} title="Экспорт PNG">
              <Download size={17} />
            </button>
          </div>
          <div className="tool-grid three">
            <button onClick={addPointAfterSelected} title="Добавить точку после выбранной вершины">
              <Plus size={17} /> точка
            </button>
            <button onClick={snapSelectedPoint} title="Примагнитить выбранную точку к ближайшей границе">
              <Magnet size={17} /> магнит
            </button>
            <button onClick={deleteSelectedPoint} title="Удалить выбранную вершину" className="danger">
              <Minus size={17} /> точка
            </button>
          </div>
          <button onClick={() => setLabels(!labels)}>
            {labels ? <EyeOff size={16} /> : <Eye size={16} />} подписи
          </button>
          <label className="upload-button">
            <Upload size={16} />
            <span>Загрузить карту</span>
            <input type="file" accept="image/*" onChange={(event) => upload(event.target.files?.[0])} />
          </label>
        </section>

        <section className="panel">
          <label>Выбрано</label>
          {selectedState && (
            <>
              <strong>{selectedState.name}</strong>
              <span className="badge">цель расширения: {selectedState.short_name}</span>
            </>
          )}
          {selected ? (
            <>
              <strong>{selected.name}</strong>
              <span className="badge">{selected.type}</span>
              <span className="badge">{selectedPointIndex === null ? 'точка не выбрана' : `точка #${selectedPointIndex + 1}`}</span>
              <select value={selected.state_id || ''} onChange={(event) => saveSelected(undefined, { state_id: event.target.value ? Number(event.target.value) : null, type: event.target.value ? 'state_core' : 'neutral', status: event.target.value ? 'active' : 'neutral' })}>
                <option value="">нейтральная</option>
                {states.map((state) => (
                  <option key={state.id} value={state.id}>
                    {state.short_name} / {state.name}
                  </option>
                ))}
              </select>
              <button onClick={() => saveSelected()}>
                <MapPinned size={16} /> сохранить
              </button>
            </>
          ) : (
            <p className="microcopy">Кликните по территории</p>
          )}
        </section>

        <section className="panel">
          <label>Создать государство</label>
          <input value={mapStateForm.name} onChange={(event) => setMapStateForm({ ...mapStateForm, name: event.target.value })} placeholder="Название" required />
          <input value={mapStateForm.short_name} onChange={(event) => setMapStateForm({ ...mapStateForm, short_name: event.target.value })} placeholder="Столица" />
          <input value={mapStateForm.color} onChange={(event) => setMapStateForm({ ...mapStateForm, color: event.target.value })} type="color" />
          <button
            className={mapStateMode ? 'active' : ''}
            onClick={() => {
              if (!mapStateForm.name.trim()) {
                setStatus('Введите название государства');
                return;
              }
              setMapStateMode(!mapStateMode);
              setDrawMode(false);
              setStatePointMode(false);
            }}
            title="Следующий клик по карте создаст стартовую территорию из 3 точек"
          >
            <MapPinned size={16} /> создать в точке
          </button>
        </section>

      </aside>

      <section className="map-workbench">
        <div className="topbar">
          <div>
            <span className="status-dot" />
            {status}
          </div>
          <button onClick={() => refresh()}>
            <RefreshCcw size={16} /> обновить
          </button>
        </div>
        <div className="map-frame">
          <MapCanvas
            map={map}
            labels={labels}
            editable
            selectedId={selectedId}
            selectedStateId={selectedStateId}
            onSelect={(id) => {
              setSelectedId(id);
              setSelectedPointIndex(null);
            }}
            onStateSelect={(id) => {
              setSelectedStateId(id);
              setStatus('Государство выбрано для расширения');
            }}
            onStateMove={moveStatePoint}
            draftPoints={draftPoints}
            onDraftClick={(point) => {
              if (mapStateMode) {
                createStateAt(point);
                return;
              }
              if (statePointMode) {
                setStatePoint(point);
                setStatePointMode(false);
                setStatus('Точка государства выбрана');
                return;
              }
              if (drawMode) setDraftPoints((current) => [...current, point]);
            }}
            onPointDrag={(territory, index, point) => {
              const points = territory.points.map((item, itemIndex) => (itemIndex === index ? point : item));
              saveSelected(points);
            }}
            selectedPointIndex={selectedPointIndex}
            onPointSelect={setSelectedPointIndex}
            statePointDraft={statePoint}
            interactionMode={interactionMode}
            draftColor={selectedState?.color}
            fillParent
            stageRef={stageRef}
            maxWidth={publicMaxWidth}
            maxHeight={publicMaxHeight}
          />
        </div>
      </section>

      <aside className="right-rail">
        <section className="panel state-panel">
          <label>Государства</label>
          {states.length === 0 && <p className="microcopy">Пока нет</p>}
          {states.map((state) => (
            <article
              key={state.id}
              className={`row-item state-row${state.id === selectedStateId ? ' active' : ''}`}
              onClick={() => {
                setSelectedStateId(state.id);
                setStatus('Государство выбрано для расширения');
              }}
            >
              <div>
                <strong>{state.short_name} / {state.name}</strong>
                <span>{state.status}</span>
              </div>
              <button
                className="danger mini-button"
                onClick={(event) => {
                  event.stopPropagation();
                  removeState(state);
                }}
                title="Удалить государство и территории"
              >
                <Trash2 size={15} />
              </button>
            </article>
          ))}
        </section>
        <section className="panel queue-panel">
          <label>Очередь действий</label>
          {actions.length === 0 && <p className="microcopy">Пока пусто</p>}
          {actions.map((action) => (
            <article key={action.id} className="row-item">
              <div>
                <strong>#{action.id} {action.type}</strong>
                <span>{action.status}</span>
              </div>
              {action.status === 'pending' && (
                <div className="mini-actions">
                  <button onClick={() => decideAction(token, action.id, 'approve').then(() => refresh())}>
                    <Check size={15} />
                  </button>
                  <button onClick={() => decideAction(token, action.id, 'reject').then(() => refresh())}>
                    <X size={15} />
                  </button>
                </div>
              )}
            </article>
          ))}
        </section>
        <section className="panel audit-panel">
          <label>Журнал</label>
          {audit.slice(0, 12).map((item) => (
            <article key={item.id} className="row-item">
              <div>
                <strong>{item.action_type}</strong>
                <span>{item.entity_type} #{item.entity_id || '-'}</span>
              </div>
            </article>
          ))}
        </section>
      </aside>
    </main>
  );
}
