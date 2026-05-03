import { NKZClient } from '@nekazari/sdk';

const getTenantId = (): string | null => {
  if (typeof window === 'undefined') return null;
  return (window as any).__nekazariAuthContext?.tenantId ?? null;
};

const getApiUrl = (): string => {
  if (typeof window !== 'undefined') {
    const env = (window as any).__ENV__;
    if (env?.VITE_API_URL) return String(env.VITE_API_URL).replace(/\/$/, '');
    if (env?.API_URL) return String(env.API_URL).replace(/\/$/, '');
    const origin = window.location.origin;
    if (origin.includes('nekazari.')) return origin.replace('nekazari.', 'nkz.');
  }
  return 'https://nkz.robotika.cloud';
};

// Generic GET/POST wrappers
export async function cueGet(path: string, params?: Record<string, string>): Promise<any> {
  const url = new URL(`${getApiUrl()}/api/modules/cue${path}`);
  if (params) Object.entries(params).forEach(([k, v]) => { if (v) url.searchParams.set(k, v); });
  const response = await fetch(url.toString(), { credentials: 'include' });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
    throw err;
  }
  return response.json();
}

export async function cuePost(path: string, data: any): Promise<any> {
  const response = await fetch(`${getApiUrl()}/api/modules/cue${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw body;
  return body;
}

export async function cuePut(path: string, data: any): Promise<any> {
  const response = await fetch(`${getApiUrl()}/api/modules/cue${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
    throw err;
  }
  return response.json().catch(() => ({}));
}

export async function cueDelete(path: string): Promise<void> {
  const response = await fetch(`${getApiUrl()}/api/modules/cue${path}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
    throw err;
  }
}

// Entity endpoints
export const explotacionesApi = {
  list: (filters?: Record<string, string>) => cueGet('/explotaciones', filters),
  get: (id: string) => cueGet(`/explotaciones/${id}`),
  create: (data: any) => cuePost('/explotaciones', data),
  update: (id: string, data: any) => cuePut(`/explotaciones/${id}`, data),
  delete: (id: string) => cueDelete(`/explotaciones/${id}`),
  listParcelas: (farmId: string) => cueGet(`/explotaciones/${farmId}/parcelas`),
};

export const parcelasApi = {
  get: (id: string) => cueGet(`/parcelas/${id}`),
  create: (data: any) => cuePost('/parcelas', data),
  update: (id: string, data: any) => cuePut(`/parcelas/${id}`, data),
  delete: (id: string) => cueDelete(`/parcelas/${id}`),
  listDeclaraciones: (parcelId: string) => cueGet(`/parcelas/${parcelId}/declaraciones`),
};

export const declaracionesApi = {
  get: (id: string) => cueGet(`/declaraciones/${id}`),
  create: (data: any) => cuePost('/declaraciones', data),
  update: (id: string, data: any) => cuePut(`/declaraciones/${id}`, data),
  delete: (id: string) => cueDelete(`/declaraciones/${id}`),
  duplicar: (id: string, campanya?: number) => cuePost(`/declaraciones/${id}/duplicar`, { campanya }),
};

export const recintosApi = {
  listByDeclaracion: (declId: string) => cueGet(`/declaraciones/${declId}/recintos`),
  get: (id: string) => cueGet(`/recintos/${id}`),
  create: (data: any) => cuePost('/recintos', data),
  createBatch: (recintos: any[]) => cuePost('/recintos/batch', { recintos }),
  update: (id: string, data: any) => cuePut(`/recintos/${id}`, data),
  delete: (id: string) => cueDelete(`/recintos/${id}`),
};

export const tratamientosApi = {
  list: (filters?: Record<string, string>) => cueGet('/tratamientos', filters),
  get: (id: string) => cueGet(`/tratamientos/${id}`),
  create: (data: any) => cuePost('/tratamientos', data),
  update: (id: string, data: any) => cuePut(`/tratamientos/${id}`, data),
  delete: (id: string) => cueDelete(`/tratamientos/${id}`),
  validate: (data: any) => cuePost('/validate', data),
};

export const fertilizacionesApi = {
  list: (filters?: Record<string, string>) => cueGet('/fertilizaciones', filters),
  get: (id: string) => cueGet(`/fertilizaciones/${id}`),
  create: (data: any) => cuePost('/fertilizaciones', data),
  update: (id: string, data: any) => cuePut(`/fertilizaciones/${id}`, data),
  delete: (id: string) => cueDelete(`/fertilizaciones/${id}`),
};

export const catalogosApi = {
  productosRopo: (filters?: Record<string, string>) => cueGet('/productos-ropo', filters),
  productoRopo: (numeroRegistro: string) => cueGet(`/productos-ropo/${numeroRegistro}`),
  productosFertilizantes: (filters?: Record<string, string>) => cueGet('/productos-fertilizantes', filters),
  productoFertilizante: (numeroRegistro: string) => cueGet(`/productos-fertilizantes/${numeroRegistro}`),
  endpointsAutonomicos: () => cueGet('/endpoints-autonomicos'),
};
